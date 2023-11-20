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

NLP = spacy.load("fr_dep_news_trf")

ANP_SERIES = pd.read_csv(ANP_PATH).astype(pd.StringDtype(storage = "pyarrow")).set_index("lemma").squeeze()
VER_SERIES = pd.read_csv(VER_PATH).astype(pd.StringDtype(storage = "pyarrow")).set_index("lemma").squeeze()
# NUM_SERIES = pd.read_csv(NUM_PATH).astype(pd.StringDtype(storage = "pyarrow")).set_index("lemma").squeeze()
NUM_SERIES = None # Le CSV doit encore être réalisé
ALL_SERIES = pd.read_csv(ALL_PATH).astype(pd.StringDtype(storage = "pyarrow")).set_index("lemma").squeeze()
# Faire la chasse aux ajectifs possessifs (update : wtf, pourquoi j'ai écrit ça ?)


# data = pd.read_csv("lynkr.csv").astype(pd.StringDtype(storage = "pyarrow"))
# data = data.sort_values(by = "lemma", key = lambda col: col.str.normalize("NFKD").str.encode("ascii", errors = "ignore").str.decode("utf-8"))
# data = data.astype(pd.StringDtype(storage = "pyarrow"))
# data.to_csv("lynkr.csv", index = False)


def tokenize(text: str, nlp: spacy.lang.fr.French) -> list[dict[str, str | None]]:
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


def translate(tokens: list[dict[str, str | None]]) -> str:

    def apply_case(text: str, shape: str) -> str:

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
        spaced_texts = [texts[0]]

        if len(texts) > 1:
            for text in texts[1:]:
            # Je peux sûrement faire quelque chose de plus propre ici
                if (text not in ('"', ")", ",", "-", ".", "]", "}")) and (spaced_texts[-1] not in ('"', "(", "-", "]", "}")):
                    spaced_texts.append(" ")
                elif (text == '"') and (spaced_texts.count('"')%2 == 0):
                    spaced_texts.append(" ")
                elif (text not in (")", ",", "-", ".", "]", "}")) and (spaced_texts[-1] == '"') and (spaced_texts.count('"')%2 == 0):
                    spaced_texts.append(" ")
                spaced_texts.append(text)

        return spaced_texts

    def translate_au_revoir(shapes: tuple[str, str]) -> tuple[str, str]:
        translated_tokens = (apply_case("paers", shapes[0]), apply_case("esperita", shapes[1]))

        return translated_tokens

    def translate_peut_etre(shape: str) -> str:
        translated_token = apply_case("pyeséa", shape)

        return translated_token

    def translate_adj_noun_propn(token: dict[str, str | None], series: pd.core.series.Series = ANP_SERIES) -> str:
        lemma = token["lemma"]
        shape = token["shape"]

        if lemma in series.index:
            translated_token = series[lemma]
            if (token["number"] == "Plur") and (translated_token[-1] != "s"):
                translated_token += "s"
            translated_token = apply_case(translated_token, shape)
        else:
            # Ajouter une fonctionnalitée de recherche de synonymes
            translated_token = "**" + apply_case(token["text"], shape) + "**"

        return translated_token

    def translate_verb_aux(token: dict[str, str | None], negation: bool, series: pd.core.series.Series = VER_SERIES) -> str:
        lemma = token["lemma"]
        shape = token["shape"]

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

        return translated_token

    def translate_num(token: dict[str, str | None], series: pd.core.series.Series = NUM_SERIES) -> str:
        text = token["text"]
        shape = token["shape"]

        if "d" in shape:
            translated_token = text
        else:
            try:
                numbered_token = text2num(token["lemma"], lang = "fr", relaxed = True)
                # Créer une opération num2word pour le Lynkr
                translated_token = str(numbered_token)
            except:
                translated_token = "**" + apply_case(text, shape) + "**"

        return translated_token

    def translate_punct(token: dict[str, str | None]) -> str:
        translated_token = token["text"]

        return translated_token

    def translate_default(token: dict[str, str | None], series: pd.core.series.Series = ALL_SERIES) -> str:
        lemma = token["lemma"]
        shape = token["shape"]

        if lemma in series.index:
            translated_token = apply_case(series[lemma], shape)
        else:
            # Ajouter une fonctionnalitée de recherche de synonymes
            translated_token = "**" + apply_case(token["text"], shape) + "**"

        return translated_token

    translated_tokens = []
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
            translated_tokens.append(translate_adj_noun_propn(token))

        elif token["pos"] in ("VERB", "AUX"):
            translated_tokens.append(translate_verb_aux(token))

        elif token["pos"] == "NUM":
            translated_tokens.append(translate_num(token))

        elif token["pos"] == "PUNCT":
            translated_tokens.append(translate_punct(token))

        else:
            translated_tokens.append(translate_default(token))



# DEPRECATED
def translate(tokens: List[Dict[str, str]]) -> Tuple[str, List[Dict[str, str]]]:
    # Ajouter nombres, ignorances des noms propres inconnus, "au revoir",
    # "race + sehr", "en-", "En-Bas", "peut-être", "quelque chose", "quelqu'un",
    # "re-", "s'il te plaît", "s'il vous plaît", "vol/voler"
    translation, not_translated = list(), list()
    negation = False
    for token in tokens:

        # Traitement de "au revoir"
        if (token["text"].lower() == "revoir") and (translation[-1] == " ") and (translation[-2].lower() == "au"):
            translation = translation[:-2]
            translated = "paers esperita"

        # Traitement de "peut-être"
        elif (token["text"].lower() == "peut") and (translation[-1] == "-") and (translation[-2].lower() == "être"):
            translation = translation[:-2]
            translated = "pyeséa"

        # Traitement de la négation
        elif token["text"].lower() in ["ne", "n'", "ni"]:
            translated = ""
            negation = True
        elif (token["text"].lower() == "pas") and (token["pos"] == "ADV"):
            translated = ""

        # Traitement des adjectifs, noms et noms propres
        elif token["pos"] in ["ADJ", "NOUN", "PROPN"]:
            df = df_ANP
            lemma = token["lemma"]
            df_lemma = df["lemma"]
            if lemma in df_lemma.values:
                translated = (df[df_lemma == lemma]['lynkr']).values[0]
                if (token["number"] == "Plur") and (translated[-1] != "s"):
                    translated = "".join([translated, "s"])
            else:
                translated = "".join(["**", token["text"], "**"])
                not_translated.append(token)

        # Traitement des verbes et auxilliaires
        elif token["pos"] in ["VERB", "AUX"]:
            df = df_VER
            lemma = token["lemma"]
            df_lemma = df["lemma"]
            prefix = ""
            if negation:
                prefix = "fran-"
            if lemma == "mourir":
                translated = prefix.join(["", "mortilem"])
            elif lemma == "vivre":
                translated = prefix.join(["", "virvilem"])
            elif lemma in df_lemma.values:
                translated = prefix.join(["", (df[df_lemma == lemma]['lynkr']).values[0]])
                if token["tense"] == "Pres":
                    translated = translated[:-1]
                elif token["tense"] == "Past":
                    translated = "".join([translated[:-1], "p"])
                elif token["tense"] == "Fut":
                    translated = "".join([translated[:-1], "f"])
            else:
                translated = "".join(["**", token["text"], "**"])
                not_translated.append(token)
            negation = False

        # Traitement des nombres
        elif token["pos"] == "NUM":
            # df = df_NUM
            if "d" in token["shape"]:
                translated = token["text"]
            else:
                lemma = token["lemma"]
                try:
                    number = text2num(lemma, lang = "fr", relaxed = True)
                    translated = str(number)
                except:
                    translated = "".join(["**", token["text"], "**"])
                    not_translated.append(token)
                # Créer une bibliothèque num2word pour le Lynkr

        # Traitement de la ponctuation
        elif token["pos"] == "PUNCT":
            translated = token["text"]
            negation = False

        # Traitement par défaut
        else:
            df = df_ALL
            lemma = token["text"]
            df_lemma = df["lemma"]
            if lemma in df_lemma.values:
                translated = (df[df_lemma == lemma]['lynkr']).values[0]
            else:
                translated = "".join(["**", token["text"], "**"])
                not_translated.append(token)

        # Gestion de la casse
        if token["shape"].islower():
            pass
        elif token["shape"].istitle():
            translated = translated.title()
        elif token["shape"].isupper():
            translated = translated.upper()
        else:
            translated = translated.capitalize()

        # Gestion des espaces
        # Penser à ajouter la gestion des espaces pour le caractère '"'
        if len(translated) != 0:
            if (translated[0] in [".", ",", "-", ")", "]", "}"]) and (translation[-1] == " "):
                translation = translation[:-1]
            translation.append(translated)
            if (translated[0] not in ["-", "(", "[", "{"]):
                translation.append(" ")

    translation = "".join(translation)
    return translation, not_translated



class Lynkr(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name = "lynkr", description = "Traduit le texte en Lynkr")
    async def lynkr_slash(self, interaction: discord.Interaction, text: str):
        await interaction.response.defer(ephemeral = True)
        member = interaction.user
        role = get(member.guild.roles, name = "Détenteur du Codex")
        translation, not_translated = translate(parse(text))

        # Réponse envoyée à l'utilisateur
        if member in role.members:
            await interaction.followup.send(translation)
        else:
            await interaction.followup.send("Il semble que tu ne sois pas encore en possession du Codex des Anciens. Si tu souhaites t'en emparer, essayes donc la commande /codex !")

        # Données d'erreurs enregistrées pour l'opérateur (c'est moi hi hi hi)
        text, lemma, pos = list(), list(), list()
        for token in not_translated:
            text.append(token["text"])
            lemma.append(token["lemma"])
            pos.append(token["pos"])
        df = pd.DataFrame({"text": text, "lemma": lemma, "pos": pos})
        df.to_csv("./meta/improvements.csv", header = False, index = False, mode = "a")



async def setup(bot):
    await bot.add_cog(Lynkr(bot))
