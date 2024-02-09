from pathlib import Path
import logging
from typing import Optional, Tuple, List, Dict

import discord
from discord import app_commands
from discord.ext import commands
from discord.utils import get

import pandas as pd
from pandas import Series
import spacy
from spacy import Language
from spacy.tokens import Token, Span, Doc
from text_to_num import text2num
import requests
from bs4 import BeautifulSoup

MAIN_FOLDER = Path(__file__).parent.parent.resolve()

LYNKR_SERIES = {"adj_noun_propn": pd.read_csv(MAIN_FOLDER / "assets/texts/csv/lynkr/adj-noun-propn.csv").astype(
                    pd.StringDtype("pyarrow")).set_index("lemma").squeeze(),
                "verb_aux": pd.read_csv(MAIN_FOLDER / "assets/texts/csv/lynkr/verb-aux.csv").astype(
                    pd.StringDtype("pyarrow")).set_index("lemma").squeeze(),
                "num": None,
                "others": pd.read_csv(MAIN_FOLDER / "assets/texts/csv/lynkr/others.csv").astype(
                    pd.StringDtype("pyarrow")).set_index("lemma").squeeze()}
# "num": pd.read_csv(MAIN_FOLDER / "assets/texts/csv/lynkr/num.csv").astype(pd.StringDtype("pyarrow")).set_index(
# "lemma").squeeze() Hunting for possessive adjectives (update: wtf, why did I write that?)

MEMORY_PATH = MAIN_FOLDER / "assets/texts/csv/lynkr/memory.csv"

NLP = spacy.load("fr_core_news_md")


logger = logging.getLogger("spacy")
logger.setLevel(logging.ERROR)


class TokenDict:
    """"""

    text: str
    lemma: str
    shape: str
    pos: str
    number: Optional[str] = None
    tense: Optional[str] = None
    polarity: Optional[str] = None
    sentence: Optional[Doc] = None
    synonyms: Optional[Tuple[Optional[str], ...]] = None
    lynkr: Optional[str] = None

    def __init__(self, token: Token, sentence: Optional[Span] = None):
        self.text = token.text
        self.lemma = token.lemma_
        self.shape = token.shape_
        self.pos = token.pos_

        morph = token.morph.to_dict()
        if "Number" in morph:
            self.number = morph["Number"]
        if "Tense" in morph:
            self.tense = morph["Tense"]
        if "Polarity" in morph:
            self.polarity = morph["Polarity"]

        if sentence:
            self.sentence = sentence.as_doc()

    def get_synonyms(self, nlp: Language = NLP) -> None:
        """...

        :param nlp: Text-processing pipeline
        """
        if self.pos == "PROPN":
            self.synonyms = ()
            return
        elif self.pos == "ADJ":
            response = requests.get(f"https://www.cnrtl.fr/synonymie/{self.lemma}/adjectif")
        elif self.pos == "NOUN":
            response = requests.get(f"https://www.cnrtl.fr/synonymie/{self.lemma}/substantif")
        elif self.pos in ("VERB", "AUX"):
            response = requests.get(f"https://www.cnrtl.fr/synonymie/{self.lemma}/verbe")
        elif self.pos == "ADV":
            response = requests.get(f"https://www.cnrtl.fr/synonymie/{self.lemma}/adverbe")
        elif self.pos == "INTJ":
            response = requests.get(f"https://www.cnrtl.fr/synonymie/{self.lemma}/interjection")
        else:
            response = requests.get(f"https://www.cnrtl.fr/synonymie/{self.lemma}")
        soup = BeautifulSoup(response.content, "html.parser")

        synonyms = map(lambda x: x.a.text, soup.find_all("td", attrs={"class": "syno_format"}))
        sorted_synonyms = sorted(nlp.pipe(synonyms), key=lambda x: x.similarity(self.sentence), reverse=True)

        self.synonyms = tuple(map(lambda x: x.text, sorted_synonyms))

    # Remove Optional when num series created | Make it TypedDict ?
    def get_lynkr(self, negation: bool = False, lynkr_series: Dict[str, Optional[Series]] = LYNKR_SERIES) -> bool:
        """...

        :param negation: ...
        :param lynkr_series: ...
        :return: ...
        """
        is_negative = negation

        def translate_adj_noun_propn(series: Series = lynkr_series["adj_noun_propn"]) -> None:
            """...

            :param series: ...
            """
            is_translated = False

            if self.lemma in series.index:
                self.lynkr = series[self.lemma]
                is_translated = True
            else:
                self.get_synonyms()
                for synonym in self.synonyms:
                    if synonym in series.index:
                        self.lynkr = series[synonym]
                        is_translated = True
                        break

            if is_translated:
                if (self.number == "Plur") and (self.lynkr[-1] != "s"):
                    self.lynkr += "s"

        def translate_verb_aux(series: Series = lynkr_series["verb_aux"]) -> None:
            """...

            :param series: ...
            """
            is_translated = False

            if negation:
                prefix = "fran-"
            else:
                prefix = ""

            if self.lemma == "mourir":
                self.lynkr = f"{prefix}mortilem"
            elif self.lemma == "vivre":
                self.lynkr = f"{prefix}virvilem"

            elif self.lemma in series.index:
                self.lynkr = series[self.lemma]
                is_translated = True
            else:
                self.get_synonyms()
                for synonym in self.synonyms:
                    if synonym in series.index:
                        self.lynkr = series[synonym]
                        is_translated = True
                        break

            if is_translated:
                if self.tense == "Pres":
                    self.lynkr = self.lynkr[:-1]
                elif self.tense == "Past":
                    self.lynkr = self.lynkr[:-1] + "p"
                elif self.tense == "Fut":
                    self.lynkr = self.lynkr[:-1] + "f"

        def translate_num() -> None:
            """...
            """
            if "d" in self.shape:
                self.lynkr = self.text
            else:
                try:
                    lemma_as_num = text2num(self.lemma, lang="fr", relaxed=True)
                    # Create a num2word operation for Lynkr
                    self.lynkr = str(lemma_as_num)
                except ValueError:
                    pass

        def translate_punct() -> None:
            """...
            """
            self.lynkr = self.text

        def translate_default(series: Series = lynkr_series["others"]) -> None:
            """...

            :param series: ...
            """
            if self.lemma in series.index:
                self.lynkr = series[self.lemma]
            else:
                self.get_synonyms()
                for synonym in self.synonyms:
                    if synonym in series.index:
                        self.lynkr = series[synonym]
                        break

        if self.pos in ("ADJ", "NOUN", "PROPN"):
            translate_adj_noun_propn()
        elif self.pos in ("VERB", "AUX"):
            translate_verb_aux()
            is_negative = False
        elif self.pos == "NUM":
            translate_num()
        elif self.pos == "PUNCT":
            translate_punct()
        else:
            translate_default()

        return is_negative

    def apply_case_to_lynkr(self) -> None:
        """...
        """
        if self.lynkr:
            if self.shape.islower():
                self.lynkr = self.lynkr.lower()
            elif self.shape.istitle():
                self.lynkr = self.lynkr.title()
            elif self.shape.isupper():
                self.lynkr = self.lynkr.upper()
            else:
                self.lynkr = self.lynkr.capitalize()


def tokenize_text(text: str, nlp: Language = NLP) -> Tuple[TokenDict, ...]:
    """Tokenizes text.

    :param text: ...
    :param nlp: ...
    :return: ...
    """
    doc = nlp(text)
    tokens = []

    for sentence in doc.sents:
        for token in sentence:
            token_dict = TokenDict(token, sentence)
            tokens.append(token_dict)

    return tuple(tokens)


def translate_tokens(tokens: Tuple[TokenDict, ...]) -> None:
    """...

    :param tokens: ...
    """
    negation = False
    for token in tokens:
        if token.text in ("ne", "n'", "ni"):
            token.lynkr = ""
            negation = True
        elif token.text == "pas" and token.pos == "ADV":
            token.lynkr = ""
        else:
            negation = token.get_lynkr(negation)


def apply_spaces_to_texts(texts: List[Optional[str]]) -> str:
    """...

    :param texts: ...
    :return: ...
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

    return "".join(spaced_texts)


def translate_text(text: str, nlp: Language = NLP) -> Tuple[str, Tuple[TokenDict, ...]]:
    """...

    :param text: ...
    :param nlp: ...
    :return: ...
    """
    tokens = tokenize_text(text, nlp)
    translate_tokens(tokens)

    lynkr_texts = []
    untranslated_tokens = []
    for i, token in enumerate(tokens):

        if i < len(tokens) - 2:
            if token.text == "peut" and tokens[i + 1].text == "-" and tokens[i + 1].text == "être":
                token.lynkr = "pyeséa"
                tokens[i + 1].lynkr = ""
                tokens[i + 2].lynkr = ""

        elif i < len(tokens) - 1:
            if token.text == "au" and tokens[i + 1].text == "revoir":
                token.lynkr = "paers"
                tokens[i + 1].lynkr = "esperita"

        token.apply_case_to_lynkr()

        if token.lynkr:
            lynkr_texts.append(token.lynkr)
        else:
            lynkr_texts.append(f"**{token.text}**")
            untranslated_tokens.append(token)

    translated_text = apply_spaces_to_texts(lynkr_texts)

    return translated_text, tuple(untranslated_tokens)


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
        """...
        """
        print("Lynkr cog loaded")

    @app_commands.command(name="lynkr", description="Traduit en Lynkr, un texte écrit en Commun")
    @app_commands.guild_only()
    async def lynkr_slash(self, interaction: discord.Interaction, texte: str) -> None:
        """Translates text from `Commun` to `Lynkr`.

        :param interaction: User-triggered slash command
        :param texte: User-entered text in the slash command
        """
        await interaction.response.defer(ephemeral=True)
        member = interaction.user
        role = get(member.guild.roles, name="Codex")

        if member in role.members:
            translated_text, untranslated_tokens = translate_text(texte)
            await interaction.followup.send(translated_text)

            text, lemma, shape, pos, number, tense, polarity, synonyms = [], [], [], [], [], [], [], []
            for token in untranslated_tokens:
                text.append(token.text)
                lemma.append(token.lemma)
                shape.append(token.shape)
                pos.append(token.pos)
                number.append(token.number)
                tense.append(token.tense)
                polarity.append(token.polarity)
                synonyms.append(" ; ".join(token.synonyms))
            df = pd.DataFrame(
                {"text": text, "lemma": lemma, "shape": shape, "pos": pos, "number": number, "tense": tense,
                 "polarity": polarity, "synonyms": synonyms})
            df.to_csv(MEMORY_PATH, header=False, index=False, mode="a")

        else:
            await interaction.followup.send(f"Il te faut le rôle {role.mention} pour utiliser cette commande.")


async def setup(bot: commands.Bot) -> None:
    """...
    """
    await bot.add_cog(Lynkr(bot))
