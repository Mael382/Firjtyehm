import discord

from discord import app_commands
from discord.ext import commands
from discord.utils import get

import spacy
import pandas as pd
from text_to_num import text2num
# from num2words import num2words


ANP_PATH = "./codex/lynkrANP.csv"
VER_PATH = "./codex/lynkrVER.csv"
NUM_PATH = "./codex/lynkrNUM.csv"
ALL_PATH = "./codex/lynkrALL.csv"
NOT_PATH = "./meta/untranslated.csv"

NLP = spacy.load("fr_dep_news_trf")

ANP_SERIES = pd.read_csv(ANP_PATH).astype(pd.StringDtype(storage = "pyarrow")).set_index("lemma").squeeze()
VER_SERIES = pd.read_csv(VER_PATH).astype(pd.StringDtype(storage = "pyarrow")).set_index("lemma").squeeze()
# NUM_SERIES = pd.read_csv(NUM_PATH).astype(pd.StringDtype(storage = "pyarrow")).set_index("lemma").squeeze()
NUM_SERIES = None # Le CSV doit encore être réalisé
ALL_SERIES = pd.read_csv(ALL_PATH).astype(pd.StringDtype(storage = "pyarrow")).set_index("lemma").squeeze()
# Faire la chasse aux ajectifs possessifs (update : wtf, pourquoi j'ai écrit ça ?)

CODEX_ROLE_NAME = "Codex"


# data = pd.read_csv("lynkr.csv").astype(pd.StringDtype(storage = "pyarrow"))
# data = data.sort_values(by = "lemma", key = lambda col: col.str.normalize("NFKD").str.encode("ascii", errors = "ignore").str.decode("utf-8"))
# data = data.astype(pd.StringDtype(storage = "pyarrow"))
# data.to_csv("lynkr.csv", index = False)


def tokenize(text: str, nlp: spacy.lang.fr.French) -> list[dict[str, str | None]]:
    """
    Tokenise un texte "Commun" sur les attributs suivants, lorsqu'ils existent : le texte, le lemme, le tag, la casse, le nombre, le temps et la polarité.
    Arguments:
        text: Texte "Commun" à tokenizer.
        nlp: Pipeline SpaCy de tokenisation.
    Returns:
        La liste des tokens du texte "Commun".
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

def translate(tokens: list[dict[str, str | None]]) -> tuple[str, list[dict[str, str | None]]]:
    """
    Traduit et recompose une liste de tokens "Commun" en "Lynkr", lorsque la traduction existe.
    Arguments:
        tokens: Liste de tokens "Commun".
    Returns:
        La traduction du texte engendrant la liste de tokens et la liste des tokens non traduits.
    """

    def apply_case(text: str, shape: str) -> str:
        """
        Applique la casse au texte.
        Arguments:
            text: Texte à formater.
            shape: Format de casse à appliquer.
        Returns:
            Le texte formaté au niveau de la casse.
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

    def apply_spaces(texts: list[str]) -> list[str]:
        """
        Ajoute des espaces aux éléments d'un texte.
        Arguments:
            texts: Liste de fragments de texte.
        Returns:
            La liste des fragments de texte formatés au niveau des espaces.
        """

        spaced_texts = [texts[0]]

        if len(texts) > 1:
            for text in texts[1:]:
            # Je peux sûrement faire quelque chose de plus propre ici
                if (text not in ("\"", ")", ",", "-", ".", "]", "}")) and (spaced_texts[-1] not in ("\"", "(", "-", "]", "}")):
                    spaced_texts.append(" ")
                elif (text == ("\"") and (spaced_texts.count("\"")%2 == 0):
                    spaced_texts.append(" ")
                elif (text not in (")", ",", "-", ".", "]", "}")) and (spaced_texts[-1] == "\"") and (spaced_texts.count("\"")%2 == 0):
                    spaced_texts.append(" ")
                spaced_texts.append(text)

        return spaced_texts

    # Ajouter la règle de l'ordre
    def translate_au_revoir(shapes: tuple[str, str]) -> tuple[str, str]:
        """
        Traduit en "Lynkr" le texte "au revoir" en "Commun", sans respecter la règle de l'ordre.
        Arguments:
            shapes: Couple de casses à appliquer.
        Returns:
            Texte "paers esperita" formaté au niveau de la casse.
        """

        translated_tokens = (apply_case("paers", shapes[0]), apply_case("esperita", shapes[1]))

        return translated_tokens

    def translate_peut_etre(shape: str) -> str:
        """
        Traduit en "Lynkr" le texte "peut-être" en "Commun".
        Arguments:
            shape: Casse à appliquer.
        Returns:
            Texte "pyeséa" formaté au niveau de la casse.
        """

        translated_token = apply_case("pyeséa", shape)

        return translated_token

    def translate_adj_noun_propn(token: dict[str, str | None], series: pd.core.series.Series = ANP_SERIES) -> tuple[str, bool]:
        """
        Traduit en "Lynkr" les adjectifs, les noms communs et les noms propres en "Commun".
        Arguments:
            token: ...
            series: ...
        Returns:
            ...
        """

        lemma = token["lemma"]
        shape = token["shape"]
        correctly_translated = True

        if lemma in series.index:
            translated_token = series[lemma]
            if (token["number"] == "Plur") and (translated_token[-1] != "s"):
                translated_token += "s"
            translated_token = apply_case(translated_token, shape)
        else:
            # Ajouter une fonctionnalitée de recherche de synonymes
            translated_token = "**" + apply_case(token["text"], shape) + "**"
            correctly_translated = False

        return translated_token, correctly_translated

    def translate_verb_aux(token: dict[str, str | None], negation: bool, series: pd.core.series.Series = VER_SERIES) -> tuple[str, bool]:
        """
        Traduit en "Lynkr" les verbes et les auxiliaires en "Commun".
        Arguments:
            token: ...
            negation: ...
            series: ...
        Returns:
            ...
        """

        lemma = token["lemma"]
        shape = token["shape"]
        correctly_translated = True

        if negation:
            prefix = "fran-"
        else:
            prefix = ""

        if lemma == "mourir":
            translated_token = apply_case(prefix + "mortilem", shape)
        elif lemma == "vivre":
            translated_token = apply_case(prefix + "virvilem", shape)
        elif lemma in series.index:
            tense = token["tense"]
            translated_token = prefix + series[lemma]
            if tense == "Pres":
                translated_token = translated_token[:-1]
            elif tense == "Past":
                translated_token = translated_token[:-1] + "p"
            elif tense == "Fut":
                translated_token = translated_token[:-1] + "f"
            translated_token = apply_case(translated_token, shape)
        else:
            # Ajouter une fonctionnalitée de recherche de synonymes
            translated_token = "**" + apply_case(token["text"], shape) + "**"
            correctly_translated = False

        return translated_token, correctly_translated

    def translate_num(token: dict[str, str | None], series: pd.core.series.Series = NUM_SERIES) -> tuple[str, bool]:
        """
        Traduit en "Lynkr" les nombres en "Commun".
        Arguments:
            token: ...
            series: ...
        Returns:
            ...
        """

        text = token["text"]
        shape = token["shape"]
        correctly_translated = True

        if "d" in shape:
            translated_token = text
        else:
            try:
                numbered_token = text2num(token["lemma"], lang = "fr", relaxed = True)
                # Créer une opération num2word pour le Lynkr
                translated_token = str(numbered_token)
            except:
                translated_token = "**" + apply_case(text, shape) + "**"
                correctly_translated = False

        return translated_token, correctly_translated

    def translate_punct(token: dict[str, str | None]) -> str:
        """
        Traduit en "Lynkr" la ponctuation en "Commun".
        Arguments:
            token: ...
        Returns:
            ...
        """

        translated_token = token["text"]

        return translated_token

    def translate_default(token: dict[str, str | None], series: pd.core.series.Series = ALL_SERIES) -> tuple[str, bool]:
        """
        Traduit en "Lynkr" les textes en "Commun".
        Arguments:
            token: ...
            series: ...
        Returns:
            ...
        """

        lemma = token["lemma"]
        shape = token["shape"]
        correctly_translated = True

        if lemma in series.index:
            translated_token = apply_case(series[lemma], shape)
        else:
            # Ajouter une fonctionnalitée de recherche de synonymes
            translated_token = "**" + apply_case(token["text"], shape) + "**"
            correctly_translated = False

        return translated_token, correctly_translated

    translated_tokens = []
    untranslated_tokens = []
    penultimate_token = {"text": None, "lemma": None, "pos": None, "shape": None, "number": None, "tense": None, "polarity": None}
    antepenultimate_token = {"text": None, "lemma": None, "pos": None, "shape": None, "number": None, "tense": None, "polarity": None}
    negation = False

    for i, token in enumerate(tokens):
        if i >= 1:
            penultimate_token = tokens[i - 1]
        if i >= 2:
            antepenultimate_token = tokens[i - 2]

        if (token["text"] == "revoir") and (penultimate_token["text"] == "au"):
            translated_tokens.pop()
            translated_tokens.extend(translate_au_revoir((token["shape"], penultimate_token["shape"])))

        elif (token["text"] == "être") and (penultimate_token["text"] == "-") and (antepenultimate_token["text"] == "peut"):
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
            translated_token, correctly_translated = translate_verb_aux(token)
            translated_tokens.append(translated_token)
            if not correctly_translated:
                untranslated_tokens.append(token)

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
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name = "lynkr", description = "Traduit en Lynkr, un texte écrit en Commun")
    async def lynkr_slash(self, interaction: discord.Interaction, text: str):
        await interaction.response.defer(ephemeral = True)
        member = interaction.user
        role = get(member.guild.roles, name = CODEX_ROLE_NAME)
        translation, untranslated_tokens = translate(tokenize(text))

        if member in role.members:
            await interaction.followup.send(translation)
        else:
            await interaction.followup.send(f"Tu ne possèdes pas encore le rôle **{CODEX_ROLE_NAME}**, nécessaire pour faire usage du traducteur.\nPour l'obtenir, tu peux utiliser la commande */codex* et rentrer le mantra du Codex des Anciens !")
        
        text, lemma, pos, shape, number, tense, polarity = [], [], [], [], [], [], []
        for untranslated_token in untranslated_tokens:
            text.append(untranslated_token["text"])
            lemma.append(untranslated_token["lemma"])
            pos.append(untranslated_token["pos"])
            shape.append(untranslated_token["shape"])
            number.append(untranslated_token["number"])
            tense.append(untranslated_token["tense"])
            polarity.append(untranslated_token["polarity"])
        df = pd.DataFrame({"text": text, "lemma": lemma, "pos": pos, "shape": shape, "number": number, "tense": tense, "polarity": polarity})
        df.to_csv(NOT_PATH, header = False, index = False, mode = "a")


async def setup(bot):
    await bot.add_cog(Lynkr(bot))
