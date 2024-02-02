import os
from dotenv import load_dotenv
from typing import Tuple, List, Dict

import discord
from discord import app_commands
from discord.ext import commands
from discord.utils import get

from text_to_num import text2num
import pandas as pd
import spacy
import requests
from bs4 import BeautifulSoup


load_dotenv()


ANP_SERIES = pd.read_csv(os.getenv("LYNKR_ANP_PATH")).astype(pd.StringDtype("pyarrow")).set_index("lemma").squeeze()
VER_SERIES = pd.read_csv(os.getenv("LYNKR_VER_PATH")).astype(pd.StringDtype("pyarrow")).set_index("lemma").squeeze()
# NUM_SERIES = pd.read_csv(os.getenv("LYNKR_NUM_PATH")).astype(pd.StringDtype("pyarrow")).set_index("lemma").squeeze()
NUM_SERIES = None  # The CSV has yet to be completed
ALL_SERIES = pd.read_csv(os.getenv("LYNKR_ALL_PATH")).astype(pd.StringDtype("pyarrow")).set_index("lemma").squeeze()
# Hunting for possessive ajectives (update: wtf, why did I write that?)

MEM_PATH = os.getenv("LYNKR_MEM_PATH")

NLP = spacy.load("fr_core_news_lg")


def tokenize(text: str, nlp: spacy.lang.fr.French = NLP) -> List[Dict[str, str | None]]:
    """Tokenize text on the following attributes, where they exist: text, lemma, tag, case, number, tense and polarity.

    :param text: Text to tokenize
    :param nlp: Natural language processing model
    :return: List of tokens
    """
    doc = nlp(text)
    tokens = []

    for token in doc:
        new_token = {"text": token.lower_,
                     "lemma": token.lemma_,
                     "pos": token.pos_,
                     "shape": token.shape_,
                     "number": None,
                     "tense": None,
                     "polarity": None}

        morph = token.morph.to_dict()
        if "Number" in morph:
            new_token["number"] = morph["Number"]
        if "Tense" in morph:
            new_token["tense"] = morph["Tense"]
        if "Polarity" in morph:
            new_token["polarity"] = morph["Polarity"]

        tokens.append(new_token)

    return tokens


def translate(tokens: List[Dict[str, str | None]]) -> Tuple[str, List[Dict[str, str | None]]]:
    """Translates and joins a list of `Commun` tokens in `Lynkr`, when the translation exists.

    :param tokens: List of tokens
    :return: Translation of the text generating the list of tokens and the list of untranslated tokens
    """

    def apply_case(text: str, shape: str) -> str:
        """Applies case to text.

        :param text: Text to format
        :param shape: Case to be applied
        :return: Case-formatted text
        """
        if shape.islower():
            cased_text = text.lower()
        elif shape.istitle():
            cased_text = text.title()
        elif shape.isupper():
            cased_text = text.upper()
        else:
            cased_text = text.capitalize()

        return cased_text

    def apply_spaces(texts: List[str]) -> List[str]:
        """Adds spaces to text elements.

        :param texts: List of text fragments
        :return: The list of space-formatted text fragments
        """
        spaced_texts = [texts[0]]

        if len(texts) > 1:
            for text in texts[1:]:
                # Surely I can do something cleaner here
                if (text not in ("\"", ")", ",", "-", ".", "]", "}")) and (
                        spaced_texts[-1] not in ("\"", "(", "-", "]", "}")):
                    spaced_texts.append(" ")
                elif text == "\"" and spaced_texts.count("\"") % 2 == 0:
                    spaced_texts.append(" ")
                elif (text not in (")", ",", "-", ".", "]", "}")) and (spaced_texts[-1] == "\"") and (
                        spaced_texts.count("\"") % 2 == 0):
                    spaced_texts.append(" ")
                spaced_texts.append(text)

        return spaced_texts

    def get_synonyms(token: Dict[str, str | None]) -> Tuple[str, ...]:
        """...

        :param token: ...
        :return: ...
        """
        pos = token["pos"]
        lemma = token["lemma"]
        if pos == "NOUN":
            response = requests.get(f"https://www.cnrtl.fr/synonymie/{lemma}/substantif")
        elif pos == "ADJ":
            response = requests.get(f"https://www.cnrtl.fr/synonymie/{lemma}/adjectif")
        elif pos in ("VERB", "AUX"):
            response = requests.get(f"https://www.cnrtl.fr/synonymie/{lemma}/verbe")
        elif pos == "ADV":
            response = requests.get(f"https://www.cnrtl.fr/synonymie/{lemma}/adverbe")
        elif pos == "INTJ":
            response = requests.get(f"https://www.cnrtl.fr/synonymie/{lemma}/interjection")
        else:
            response = requests.get(f"https://www.cnrtl.fr/synonymie/{lemma}")
        soup = BeautifulSoup(response.content, "html.parser")
        synonyms = tuple(map(lambda x: x.a.text, soup.find_all("td", attrs={"class": "syno_format"})))

        return synonyms

    def translate_au_revoir(shapes: Tuple[str, str]) -> Tuple[str, str]:
        """Translates the text "au revoir" into `Lynkr`, without respecting the order rule.

        :param shapes: Cases to be applied
        :return: Case-sensitive text "paers esperita"
        """
        # Add the order rule
        translated_tokens = (apply_case("paers", shapes[0]), apply_case("esperita", shapes[1]))

        return translated_tokens

    def translate_peut_etre(shape: str) -> str:
        """Translates the text "peut-être" into `Lynkr`.

        :param shape: Case to be applied
        :return: Case-sensitive text "pyeséa".
        """
        translated_token = apply_case("pyeséa", shape)

        return translated_token

    def translate_adj_noun_propn(token: Dict[str, str | None], series: pd.core.series.Series = ANP_SERIES) -> Tuple[
        str, bool]:
        """Translates adjectives, nouns and pronouns into `Lynkr`.

        :param token: ...
        :param series: ...
        :return: ...
        """
        lemma = token["lemma"]
        shape = token["shape"]
        translated_lemma = None
        is_translated = True

        if lemma in series.index:
            translated_lemma = series[lemma]
        else:
            synonyms = get_synonyms(token)
            for synonym in synonyms:
                if synonym in series.index:
                    translated_lemma = series[synonym]
                    break
        if translated_lemma:
            if (token["number"] == "Plur") and (translated_lemma[-1] != "s"):
                translated_lemma += "s"
            translated_token = apply_case(translated_lemma, shape)
        else:
            translated_token = "**" + apply_case(token["text"], shape) + "**"
            is_translated = False

        return translated_token, is_translated

    def translate_verb_aux(token: Dict[str, str | None], negation: bool, series: pd.core.series.Series = VER_SERIES) -> \
            Tuple[str, bool]:
        """Translates verbs and auxiliaries into `Lynkr`.

        :param token: ...
        :param negation: ...
        :param series: ...
        :return: ...
        """
        lemma = token["lemma"]
        shape = token["shape"]
        translated_lemma = None
        is_translated = True

        if negation:
            prefix = "fran-"
        else:
            prefix = ""

        if lemma == "mourir":
            translated_token = apply_case(prefix + "mortilem", shape)
        elif lemma == "vivre":
            translated_token = apply_case(prefix + "virvilem", shape)
        elif lemma in series.index:
            translated_lemma = series[lemma]
        else:
            synonyms = get_synonyms(token)
            for synonym in synonyms:
                if synonym in series.index:
                    translated_lemma = series[synonym]
                    break
        if translated_lemma:
            tense = token["tense"]
            translated_lemma = f"{prefix}{translated_lemma}"
            if tense == "Pres":
                translated_lemma = translated_lemma[:-1]
            elif tense == "Past":
                translated_lemma = translated_lemma[:-1] + "p"
            elif tense == "Fut":
                translated_lemma = translated_lemma[:-1] + "f"
            translated_token = apply_case(translated_lemma, shape)
        else:
            translated_token = "**" + apply_case(token["text"], shape) + "**"
            is_translated = False

        return translated_token, is_translated

    def translate_num(token: Dict[str, str | None], series: pd.core.series.Series = NUM_SERIES) -> Tuple[str, bool]:
        """Translates numbers into `Lynkr`.

        :param token: ...
        :param series: ...
        :return: ...
        """
        text = token["text"]
        shape = token["shape"]
        is_translated = True

        if "d" in shape:
            translated_token = text
        else:
            try:
                numbered_token = text2num(token["lemma"], lang="fr", relaxed=True)
                # Create a num2word operation for Lynkr
                translated_token = str(numbered_token)
            except:
                translated_token = "**" + apply_case(text, shape) + "**"
                is_translated = False

        return translated_token, is_translated

    def translate_punct(token: Dict[str, str | None]) -> str:
        """Translates punctuation into `Lynkr`.

        :param token: ...
        :return: ...
        """
        translated_token = token["text"]

        return translated_token

    def translate_default(token: Dict[str, str | None], series: pd.core.series.Series = ALL_SERIES) -> Tuple[str, bool]:
        """Translates texts into "Lynkr".

        :param token: ...
        :param series: ...
        :return: ...
        """
        lemma = token["lemma"]
        shape = token["shape"]
        translated_lemma = None
        is_translated = True

        if lemma in series.index:
            translated_lemma = series[lemma]
        else:
            synonyms = get_synonyms(token)
            for synonym in synonyms:
                if synonym in series.index:
                    translated_lemma = series[synonym]
                    break
        if translated_lemma:
            translated_token = apply_case(translated_lemma, shape)
        else:
            translated_token = "**" + apply_case(token["text"], shape) + "**"
            is_translated = False

        return translated_token, is_translated

    translated_tokens = []
    untranslated_tokens = []
    penultimate_token = {"text": None, "lemma": None, "pos": None, "shape": None, "number": None, "tense": None,
                         "polarity": None}
    antepenultimate_token = {"text": None, "lemma": None, "pos": None, "shape": None, "number": None, "tense": None,
                             "polarity": None}
    negation = False

    for i, token in enumerate(tokens):
        if i >= 1:
            penultimate_token = tokens[i - 1]
        if i >= 2:
            antepenultimate_token = tokens[i - 2]

        if (token["text"] == "revoir") and (penultimate_token["text"] == "au"):
            translated_tokens.pop()
            translated_tokens.extend(translate_au_revoir((token["shape"], penultimate_token["shape"])))

        elif (token["text"] == "être") and (penultimate_token["text"] == "-") and (
                antepenultimate_token["text"] == "peut"):
            translated_tokens.pop()
            translated_tokens.pop()
            translated_tokens.append(translate_peut_etre(antepenultimate_token["shape"]))

        elif token["text"] in ("ne", "n'", "ni"):
            negation = True
        elif (token["text"] == "pas") and (token["pos"] == "ADV"):
            pass

        elif token["pos"] in ("ADJ", "NOUN", "PROPN"):
            translated_token, correctly_translated = translate_adj_noun_propn(token)
            translated_tokens.append(translated_token)
            if not correctly_translated:
                untranslated_tokens.append(token)

        elif token["pos"] in ("VERB", "AUX"):
            translated_token, correctly_translated = translate_verb_aux(token, negation)
            translated_tokens.append(translated_token)
            if not correctly_translated:
                untranslated_tokens.append(token)
            negation = False

        elif token["pos"] == "NUM":
            translated_token, correctly_translated = translate_num(token)
            translated_tokens.append(translated_token)
            if not correctly_translated:
                untranslated_tokens.append(token)

        elif token["pos"] == "PUNCT":
            translated_tokens.append(translate_punct(token))

        else:
            translated_token, correctly_translated = translate_default(token)
            translated_tokens.append(translated_token)
            if not correctly_translated:
                untranslated_tokens.append(token)

    translated_tokens = apply_spaces(translated_tokens)
    translation = "".join(translated_tokens)

    return translation, untranslated_tokens


class Lynkr(commands.Cog):
    """Discord cog for Firjtyehm containing commands related to translation from `Commun` into `Lynkr`.

    :param bot: Discord bot
    """

    def __init__(self, bot) -> None:
        """Constructor method
        """
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        print("Lynkr cog loaded")

    @app_commands.command(name="lynkr", description="Traduit en Lynkr, un texte écrit en Commun")
    @app_commands.guild_only()
    async def lynkr_slash(self, interaction: discord.Interaction, text: str) -> None:
        """Translates text from `Commun` to `Lynkr`.

        :param interaction: User-triggered slash command
        :param text: User-entered text in the slash command
        """
        await interaction.response.defer(ephemeral=True)
        member = interaction.user
        role = get(member.guild.roles, name="Codex")
        translation, untranslated_tokens = translate(tokenize(text))

        if member in role.members:
            await interaction.followup.send(translation)
        else:
            await interaction.followup.send(
                f"Tu ne possèdes pas le rôle {role.mention}.")

        text, lemma, pos, shape, number, tense, polarity = [], [], [], [], [], [], []
        for untranslated_token in untranslated_tokens:
            text.append(untranslated_token["text"])
            lemma.append(untranslated_token["lemma"])
            pos.append(untranslated_token["pos"])
            shape.append(untranslated_token["shape"])
            number.append(untranslated_token["number"])
            tense.append(untranslated_token["tense"])
            polarity.append(untranslated_token["polarity"])
        df = pd.DataFrame({"text": text, "lemma": lemma, "pos": pos, "shape": shape, "number": number, "tense": tense,
                           "polarity": polarity})
        df.to_csv(MEM_PATH, header=False, index=False, mode="a")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Lynkr(bot))
