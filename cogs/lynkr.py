import discord

from discord import app_commands
from discord.ext import commands
from discord.utils import get

import spacy
from text_to_num import text2num
# from num2words import num2words
import pandas as pd
from typing import List, Dict, Tuple

nlp = spacy.load("fr_core_news_md")
# nlp = spacy.load("fr_dep_news_trf")
df_ANP = pd.read_csv("./codex/lynkrANP.csv").astype(pd.StringDtype(storage = "pyarrow"))
df_VER = pd.read_csv("./codex/lynkrVER.csv").astype(pd.StringDtype(storage = "pyarrow"))
# df_NUM = pd.read_csv("./codex/lynkrNUM.csv").astype(pd.StringDtype(storage = "pyarrow"))
df_ALL = pd.read_csv("./codex/lynkrALL.csv").astype(pd.StringDtype(storage = "pyarrow"))
# Faire la chasse aux ajectifs possessifs

# data = pd.read_csv("lynkr.csv").astype(pd.StringDtype(storage = "pyarrow"))
# data = data.sort_values(by = "lemma", key = lambda col: col.str.normalize("NFKD").str.encode("ascii", errors = "ignore").str.decode("utf-8"))
# data = data.astype(pd.StringDtype(storage = "pyarrow"))
# data.to_csv("lynkr.csv", index = False)


def tokenize(text: str, nlp: spacy.lang.fr.French) -> list[dict[str, str | None]]:
    doc = nlp(text)
    tokens = list()

    for token in doc:
        new_token = {"text": token.lower_,
                     "lemma": token.lemma_,
                     "pos":token.pos_,
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


# deprecated
def parse(text: str) -> List[Dict[str, str]]:
    doc = nlp(text)
    tokens = list()

    for token in doc:
        new_token = {"pos":token.pos_,"lemma": token.lemma_.lower(),
                     "text": token.lower_, "shape": token.shape_, "number": None,
                     "gender": None, "tense": None, "polarity": None}
        morph = token.morph.to_dict()
        if "Number" in morph:
            new_token["number"] = morph["Number"]
        if "Gender" in morph:
            new_token["gender"] = morph["Gender"]
        if "Tense" in morph:
            new_token["tense"] = morph["Tense"]
        if "Polarity" in morph:
            new_token["polarity"] = morph["Polarity"]
        tokens.append(new_token)

    return tokens


def apply_case(token: dict[str, str | None], translated_token: str) -> str:
    shape = token["shape"]

    if shape.islower():
        cased_translated_token = translated_token.lower()
    elif shape.istitle():
        cased_translated_token = translated_token.title()
    elif shape.isupper():
        cased_translated_token = translated_token.upper()
    else:
        cased_translated_token = translated_token.capitalize()

    return cased_translated_token


def translate_au_revoir(tokens: list[dict[str, str | None]]) -> tuple(str, str):
    translated_tokens = (apply_case(tokens[0], "paers"), apply_case(tokens[1], "esperita"))

    return translated_tokens


def translate_peut_etre(tokens: list[dict[str, str | None]]) -> str:
    translated_tokens = apply_case(tokens[0], "pyeséa")

    return translated_tokens


# deprecated
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
