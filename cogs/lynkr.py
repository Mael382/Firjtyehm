from pathlib import Path
import logging
from typing import Tuple, Dict, Optional

import discord
from discord import app_commands
from discord import ui
from discord import Interaction, SelectOption
from discord.ext import commands
from discord.utils import get

import pandas as pd
import spacy
from spacy.tokens import Doc, Token
from text_to_num import text2num
import requests
from bs4 import BeautifulSoup


# Chemin vers le dossier principal du projet
MAIN_FOLDER = Path(__file__).parent.parent.resolve()

# Dictionnaire de traduction Commun -> Lynkr
LYNKR_SERIES = {"GRAMNUM": pd.read_csv(MAIN_FOLDER / "assets/texts/csv/lynkr/adj-noun-propn.csv").astype(
                    pd.StringDtype("pyarrow")).set_index("lemma").squeeze(),
                "GRAMCONJ": pd.read_csv(MAIN_FOLDER / "assets/texts/csv/lynkr/verb-aux.csv").astype(
                    pd.StringDtype("pyarrow")).set_index("lemma").squeeze(),
                "X": pd.read_csv(MAIN_FOLDER / "assets/texts/csv/lynkr/other.csv").astype(
                    pd.StringDtype("pyarrow")).set_index("lemma").squeeze()}
# Faire la chasse aux adjectifs possessifs (màj : wtf, pourquoi j'ai écrit ça ???)

# Chemin vers le fichier de mémoire
MEMORY_PATH = MAIN_FOLDER / "assets/texts/csv/lynkr/memory.csv"

# Modèle de langage pré-entrainé Spacy pour le français
NLP = spacy.load("fr_core_news_lg")


# Configuration du logger pour Spacy
logger = logging.getLogger("spacy")
logger.setLevel(logging.ERROR)


# Getter de la propriété personnalisée `lynkr_tag` pour les tokens Spacy
def lynkr_tag_getter(token: Token) -> str:
    """Fonction pour obtenir le tag Lynkr d'un token donné.

    :param token: Le token Spacy pour lequel le tag Lynkr doit être obtenu.
    :return: Le tag Lynkr pour le token donné.
    """
    # Si le token est un adjectif, un nom ou un nom propre, on lui attribue le tag Lynkr "GRAMNUM" (accord en nombre)
    if token.pos_ in ("ADJ", "NOUN", "PROPN"):
        return "GRAMNUM"
    # Si le token est un auxiliaire ou un verbe, on lui attribue le tag Lynkr "GRAMCONJ" (conjugaison en temps)
    elif token.pos_ in ("AUX", "VERB"):
        return "GRAMCONJ"
    # Si le token est un numéral, on lui attribue le tag Lynkr "NUM"
    # Si le token est une ponctuation, on lui attribue le tag Lynkr "PUNCT"
    elif token.pos_ in ("NUM", "PUNCT"):
        return token.pos_
    # Si le token est une particule de négation "ne" ou "pas", on lui attribut le tag Lynkr "PART"
    elif token.pos_ == "ADV" and token.lemma_ in ("ne", "pas"):
        return "PART"
    # Sinon, on attribue le tag Lynkr "X"
    else:
        return "X"


# Application de la propriété `lynkr_tag` aux tokens Spacy
Token.set_extension("lynkr_tag", getter=lynkr_tag_getter)


# Getter de la propriété personnalisée `lynkr_compatible_synonyms` pour les tokens Spacy
def lynkr_compatible_synonyms_getter(token: Token) -> Tuple[str] | Tuple:
    """Fonction pour obtenir les synonymes traduisibles en Lynkr d'un token donné.

    :param token: Le token Spacy pour lequel les synonymes traduisibles en Lynkr doivent être obtenus.
    :return: Un tuple contenant les synonymes traduisibles en Lynkr pour le token donné.
    """
    # Si le token est un nom propre, une ponctuation ou un symbole, il n'a pas de synonymes traduisibles Lynkr
    if token.pos_ in ("PROPN", "PUNCT", "SYM"):
        return ()

    # Si le token est un adjectif, on recherche dans le répertoire "adjectif"
    elif token.pos_ == "ADJ":
        directory = "adjectif"
    # Si le token est un nom, on recherche dans le répertoire "substantif"
    elif token.pos_ == "NOUN":
        directory = "substantif"
    # Si le token est un auxiliaire ou un verbe, on recherche dans le répertoire "verbe"
    elif token.pos_ in ("AUX", "VERB"):
        directory = "verbe"
    # Si le token est un adverbe, on recherche dans le répertoire "adverbe"
    elif token.pos_ == "ADV":
        directory = "adverbe"
    # Si le token est une interjection, on recherche dans le répertoire "interjection"
    elif token.pos_ == "INTJ":
        directory = "interjection"
    # Sinon, on ne recherche dans aucun répertoire particulier
    else:
        directory = ""

    # Récupération de la page de synonymes sur le site du CNRTL
    response = requests.get(f"https://www.cnrtl.fr/synonymie/{token.lemma_}/{directory}")
    soup = BeautifulSoup(response.content, "html.parser")

    # Extraction des synonymes de la page
    synonyms = map(lambda x: x.a.text, soup.find_all("td", attrs={"class": "syno_format"}))

    # Filtrage des synonymes pour ne conserver que ceux traduisibles en Lynkr
    translatable = frozenset(LYNKR_SERIES[
                                 token._.lynkr_tag].index.to_list())  # Je peux peut-être passer directement d'un
    # index à un frozenset, sans passer par la méthode `to_list`.
    synonyms = filter(lambda x: x in translatable, synonyms)

    return tuple(synonyms)


# Application de la propriété `lynkr_compatible_synonyms` aux tokens Spacy
Token.set_extension("lynkr_compatible_synonyms", getter=lynkr_compatible_synonyms_getter)
# Application de l'attribut `lynkr_applied_synonym` aux tokens Spacy
Token.set_extension("lynkr_applied_synonym", default=None)


# Sous-fonction de la fonction `lynkr_lemma_translation_getter`
def lynkr_lemma_translation_default(token: Token) -> Optional[str]:
    """Fonction pour obtenir la traduction du lemme en Lynkr d'un token avec le tag Lynkr `GRAMNUM`, `GRAMCONJ` ou `X`.

    :param token: Le token Spacy pour lequel la traduction du lemme en Lynkr doit être obtenue.
    :return: La traduction du lemme en Lynkr pour le token donné.
    """
    # Sélection de la série correspondant au tag Lynkr du token
    series = LYNKR_SERIES[token._.lynkr_tag]

    # Récupération des termes traduisibles Lynkr
    translatable = frozenset(series.index.to_list())
    # Si le lemme du token est traduisible, renvoyer sa traduction correspondante
    if token.lemma_ in translatable:
        return series[token.lemma_]


# Sous-fonction de la fonction `lynkr_lemma_translation_getter`
def lynkr_lemma_translation_num(token: Token) -> Optional[str]:
    """Fonction pour obtenir la traduction en Lynkr d'un token avec le tag Lynkr `NUM`.

    :param token: Le token Spacy pour lequel la traduction en Lynkr doit être obtenue.
    :return: La traduction en Lynkr pour le token donné.
    """
    # Si le token est écrit en chiffres, renvoyer son texte tel quel
    if "d" in token.shape_:
        return token.text

    # Sinon, essayer de convertir l'écriture du token en chiffres
    else:
        try:
            text_as_num = text2num(token.text, lang="fr", relaxed=True)
        except ValueError:
            pass
        else:
            return str(text_as_num)  # Implémenter une fonction num2text, pour retrouver une écriture en lettres


# Sous-fonction de la fonction `lynkr_lemma_translation_getter`
def lynkr_lemma_translation_punct(token: Token) -> str:
    """Fonction pour obtenir la traduction en Lynkr d'un token avec le tag Lynkr `PUNCT`.

    :param token: Le token Spacy pour lequel la traduction en Lynkr doit être obtenue.
    :return: La traduction en Lynkr pour le token donné.
    """
    return token.text


# Sous-fonction de la fonction `lynkr_lemma_translation_getter`
def lynkr_lemma_translation_part() -> str:
    """Fonction pour obtenir la traduction en Lynkr d'un token avec le tag Lynkr `PART`.

    :return: La traduction en Lynkr d'un token avec le tag Lynkr `PART`.
    """
    return ""


# Getter de la propriété personnalisée `lynkr_lemma_translation` pour les tokens Spacy
def lynkr_lemma_translation_getter(token: Token) -> Optional[str]:
    """Fonction pour obtenir la traduction du lemme en Lynkr d'un token donné.

    :param token: Le token Spacy pour lequel la traduction du lemme en Lynkr doit être obtenue.
    :return: La traduction du lemme en Lynkr pour le token donné.
    """
    # Si le tag Lynkr du token est parmi "GRAMNUM", "GRAMCONJ" ou "X", obtenir la traduction par défaut
    if token._.lynkr_tag in ("GRAMNUM", "GRAMCONJ", "X"):
        return lynkr_lemma_translation_default(token)
    # Si le tag Lynkr du token est "NUM", obtenir la traduction numérale
    elif token._.lynkr_tag == "NUM":
        return lynkr_lemma_translation_num(token)
    # Si le tag Lynkr du token est "PUNCT", obtenir la traduction de ponctuation
    elif token._.lynkr_tag == "PUNCT":
        return lynkr_lemma_translation_punct(token)
    # Si le tag Lynkr du token est "PART", obtenir la traduction de particule
    elif token._.lynkr_tag == "PART":
        return lynkr_lemma_translation_part()


# Application de la propriété `lynkr_lemma_translation` aux tokens Spacy
Token.set_extension("lynkr_lemma_translation", getter=lynkr_lemma_translation_getter)


#
def complete_lynkr_translation_gramnum(token: Token, lynkr: Optional[str] = None) -> Optional[str]:
    """

    :param token:
    :param lynkr:
    :return:
    """
    #
    if lynkr is None:
        translation = token._.lynkr_lemma_translation
    else:
        translation = lynkr

    #
    if translation is not None:

        #
        number = token.morph.to_dict()["Number"]
        if (number == "Plur") and (translation[-1] != "s"):
            return f"{translation}s"
        else:
            return translation


def complete_lynkr_translation_gramconj(token: Token, lynkr: Optional[str] = None) -> Optional[str]:
    """

    :param token:
    :param lynkr:
    :return:
    """
    #
    if lynkr is None:
        translation = token._.lynkr_lemma_translation
    else:
        translation = lynkr

    #
    if translation is not None:

        #
        polarity = ""
        for i in range(-1, -3, -1):
            try:
                prev_token = token.nbor(i)
            except IndexError:
                break
            else:
                if prev_token.lemma_ == "ne":
                    polarity = "fran-"
                    break

        #
        if token.lemma_ not in ("mourir", "vivre"):

            #
            tense = token.morph.to_dict()["Tense"]
            if tense == "Pres":
                return f"{polarity}{translation[:-1]}"
            elif tense == "Past":
                return f"{polarity}{translation[:-1]}p"
            elif tense == "Fut":
                return f"{polarity}{translation[:-1]}f"

        #
        return f"{polarity}{translation}"


#
def complete_lynkr_translation_x(token: Token, lynkr: Optional[str] = None) -> Optional[str]:
    """

    :param token:
    :param lynkr:
    :return:
    """
    #
    if lynkr is None:
        translation = token._.lynkr_lemma_translation
    else:
        translation = lynkr

    #
    return translation


#
def lynkr_translation_method(token: Token, synonym: Optional[str] = None) -> Optional[str]:
    """

    :param token:
    :param synonym:
    """
    translation = token._.lynkr_lemma_translation
    if token._.lynkr_tag in ("GRAMNUM", "GRAMCONJ", "X"):
        series = LYNKR_SERIES[token._.lynkr_tag]
        if translation is None:
            if synonym is not None:
                if synonym in token._.lynkr_compatible_synonyms:
                    translation = series[synonym]
                    token._.lynkr_applied_synonym = synonym
            else:
                if len(token._.lynkr_compatible_synonyms) > 0:
                    best_synonym = max(NLP.pipe(token._.lynkr_compatible_synonyms),
                                       key=lambda x: x.similarity(token.sent.as_doc())).text
                    translation = series[best_synonym]
                    token._.lynkr_applied_synonym = best_synonym
        if translation is not None:
            if token._.lynkr_tag == "GRAMNUM":
                translation = complete_lynkr_translation_gramnum(token, translation)
            elif token._.lynkr_tag == "GRAMCONJ":
                translation = complete_lynkr_translation_gramconj(token, translation)
            elif token._.lynkr_tag == "X":
                translation = complete_lynkr_translation_x(token, translation)
    return translation


Token.set_extension("get_lynkr_translation", method=lynkr_translation_method)


#
def pretranslation_commun_to_lynkr(text: str) -> Tuple[Doc, Tuple[int, ...] | Tuple]:
    """

    :param text:
    :return:
    """
    doc = NLP(text)
    synonymable = []
    for i, token in enumerate(doc):
        if token._.lynkr_lemma_translation is None and len(token._.lynkr_compatible_synonyms) > 0:
            synonymable.append(i)
    return doc, tuple(synonymable)


#
def apply_case_to_lynkr(token: Token, lynkr: str) -> str:
    """

    :param token:
    :param lynkr:
    :return:
    """
    if token.shape_.islower():
        return lynkr.lower()
    elif token.shape_.istitle():
        return lynkr.title()
    elif token.shape_.isupper():
        return lynkr.upper()
    else:
        return lynkr.capitalize()


#
def complete_translation_commun_to_lynkr(doc: Doc, synonyms: Dict[int, str]) -> Tuple[
    Tuple[str, ...], Tuple[Token, ...], Tuple[Tuple[str, str], ...]]:
    """

    :param doc:
    :param synonyms:
    :return:
    """
    synonyms_keys = frozenset(synonyms.keys())
    translation, untranslated, synonymed = [], [], []
    for i, token in enumerate(doc):
        if i in synonyms_keys:
            translation.append(apply_case_to_lynkr(token, token._.get_lynkr_translation(synonyms[i])))
            synonymed.append((token.lemma_, token._.lynkr_applied_synonym))
        elif token._.lynkr_lemma_translation is None:
            translation.append(f"`{token.text}`")
            untranslated.append(token)
        elif token._.lynkr_lemma_translation == "":
            translation.append("")
        elif i > 2 and token.lower_ == "être" and doc[i - 1].text == "-" and doc[i - 2].text == "peut":
            translation.pop()
            translation.pop()
            translation.append(apply_case_to_lynkr(doc[i - 2], "pyeséa"))
        elif i > 1 and token.lower_ == "revoir" and doc[i - 1].lower_ == "au":  # Ajouter la variante "paer amars"
            translation.pop()
            translation.append(apply_case_to_lynkr(doc[i - 1], "paers"))
            translation.append(apply_case_to_lynkr(token, "esperita"))
        else:
            translation.append(apply_case_to_lynkr(token, token._.get_lynkr_translation(None)))
    return tuple(translation), tuple(untranslated), tuple(synonymed)


#
def fast_translation_commun_to_lynkr(text: str) -> Tuple[
    Tuple[str, ...], Tuple[Token, ...], Tuple[Tuple[str, str], ...]]:
    """

    :param text:
    :return:
    """
    doc = NLP(text)
    translation, untranslated, synonymed = [], [], []
    for i, token in enumerate(doc):
        if token._.lynkr_lemma_translation is None and len(token._.lynkr_compatible_synonyms) > 0:
            translation.append(apply_case_to_lynkr(token, token._.get_lynkr_translation(None)))
            synonymed.append((token.lemma_, token._.lynkr_applied_synonym))
        elif token._.lynkr_lemma_translation is None:
            translation.append(f"`{token.text}`")
            untranslated.append(token)
        elif token._.lynkr_lemma_translation == "":
            translation.append("")
        elif i > 2 and token.lower_ == "être" and doc[i - 1].text == "-" and doc[i - 2].text == "peut":
            translation.pop()
            translation.pop()
            translation.append(apply_case_to_lynkr(doc[i - 2], "pyeséa"))
        elif i > 1 and token.lower_ == "revoir" and doc[i - 1].lower_ == "au":  # Ajouter la variante "paer amars"
            translation.pop()
            translation.append(apply_case_to_lynkr(doc[i - 1], "paers"))
            translation.append(apply_case_to_lynkr(token, "esperita"))
        else:
            translation.append(apply_case_to_lynkr(token, token._.get_lynkr_translation(None)))
    return tuple(translation), tuple(untranslated), tuple(synonymed)


#
def translation_to_text(translation: Tuple[str, ...]) -> str:
    """

    :param translation:
    :return:
    """
    text = [translation[0]]
    if len(translation) > 1:
        for word in translation[1:]:
            if (word not in ('"', ")", ",", "-", ".", "]", "}")) and (text[-1] not in ('"', "(", "-", "]", "}")):
                text.append(" ")
            elif word == '"' and text.count('"') % 2 == 0:
                text.append(" ")
            elif (word not in (")", ",", "-", ".", "]", "}")) and (text[-1] == '"') and (text.count('"') % 2 == 0):
                text.append(" ")
            text.append(word)
    return "".join(text)


#
class SynonymSelect(ui.Select):
    """"""

    def __init__(self, doc: Doc, synonymable: Tuple[int, ...]) -> None:
        placeholder = f'Choisissez un synonyme pour "{doc[synonymable[0]].text}" !'
        options = []
        for synonym in doc[synonymable[0]]._.lynkr_compatible_synonyms:
            options.append(SelectOption(label=f'"{synonym}"', value=synonym))
            print(options[-1].value, len(options[-1].value))
        options.append(SelectOption(label="Aucun synonyme", value="None",
                                    description=f'Attention : "{doc[synonymable[0]].lemma_}" ne sera pas traduit !'))
        print(options[-1].value, len(options[-1].value))

        super().__init__(placeholder=placeholder, options=options)
        self.index = 0
        self.doc = doc
        self.synonymable = synonymable
        self.selected_synonyms = []

    async def callback(self, interaction: Interaction) -> None:
        await interaction.response.defer()


class SynonymButton(ui.Button):
    """"""

    def __init__(self, select: SynonymSelect) -> None:
        super().__init__(label="Valider", style=discord.ButtonStyle.blurple)
        self.select = select
        self.translation = ""

    async def callback(self, interaction: Interaction) -> None:
        self.select.index += 1
        self.select.selected_synonyms.append(self.select.values[0])

        if self.select.index < len(self.select.synonymable):
            placeholder = f'Choisissez un synonyme pour "{self.select.doc[self.select.synonymable[self.select.index]].text}" !'
            options = []
            for synonym in self.select.doc[self.select.synonymable[self.select.index]]._.lynkr_compatible_synonyms:
                options.append(SelectOption(label=f'"{synonym}"', value=synonym))
            options.append(SelectOption(label="Aucun synonyme", value="None",
                                        description=f'Attention : "{self.select.doc[self.select.synonymable[self.select.index]].lemma_}" ne sera pas traduit !'))

            self.select.placeholder = placeholder
            self.select.options = options

        else:
            self.select.disabled = True
            self.disabled = True

            translation, untranslated, _ = complete_translation_commun_to_lynkr(self.select.doc, dict(
                zip(self.select.synonymable, self.select.selected_synonyms)))

            self.translation = translation_to_text(translation)

            text, lemma, pos, morph = [], [], [], []
            for token in untranslated:
                text.append(token.text)
                lemma.append(token.lemma_)
                pos.append(token.pos_)
                morph.append(token.morph)
            df = pd.DataFrame({"text": text, "lemma": lemma, "pos": pos, "morph": morph})
            df.to_csv(MEMORY_PATH, header=False, index=False, mode="a")

        embed = discord.Embed(title="TRADUCTION : Commun → Lynkr",
                              url="https://www.herobrine.fr/index.php?p=codex",
                              description=self.select.doc.text,
                              color=discord.Color.dark_gold())
        embed.add_field(name="Traduction",
                        value=self.translation,
                        inline=False)
        embed.add_field(name="Synonymes",
                        value="\n".join([f"{self.select.doc[j].lemma_} → {self.select.selected_synonyms[i]}" for i, j in
                                         enumerate(self.select.synonymable[:len(self.select.selected_synonyms)])]),
                        inline=False)

        await interaction.response.edit_message(embed=embed, view=self.view)


#
class SynonymView(ui.View):
    """"""

    def __init__(self, doc: Doc, synonymable: Tuple[int, ...]) -> None:
        super().__init__(timeout=None)

        select = SynonymSelect(doc, synonymable)
        button = SynonymButton(select)

        self.add_item(select)
        self.add_item(button)


class Lynkr(commands.Cog):
    """

    :param bot:
    """

    def __init__(self, bot) -> None:
        """

        :param bot:
        """
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        """
        """
        print("Lynkr cog loaded")

    @app_commands.command(name="fastlynkr", description="Traduit en Lynkr, un texte écrit en Commun")
    @app_commands.guild_only()
    async def fast_lynkr_slash(self, interaction: discord.Interaction, texte: str) -> None:
        """

        :param interaction:
        :param texte:
        """
        await interaction.response.defer(ephemeral=True)
        member = interaction.user
        role = get(member.guild.roles, name="Codex")
        if member in role.members:
            translation, untranslated, synonymed = fast_translation_commun_to_lynkr(texte)
            embed = discord.Embed(title="TRADUCTION : Commun → Lynkr",
                                  url="https://www.herobrine.fr/index.php?p=codex",
                                  description=texte,
                                  color=discord.Color.dark_gold())
            embed.add_field(name="Traduction",
                            value=translation_to_text(translation),
                            inline=False)
            if synonymed:
                embed.add_field(name="Synonymes",
                                value="\n".join([f"{synonym[0]} → {synonym[1]}" for synonym in synonymed]),
                                inline=False)
            await interaction.followup.send(embed=embed)
            text, lemma, pos, morph = [], [], [], []
            for token in untranslated:
                text.append(token.text)
                lemma.append(token.lemma_)
                pos.append(token.pos_)
                morph.append(token.morph)
            df = pd.DataFrame({"text": text, "lemma": lemma, "pos": pos, "morph": morph})
            df.to_csv(MEMORY_PATH, header=False, index=False, mode="a")
        else:
            await interaction.followup.send(f"Il te faut le rôle {role.mention} pour utiliser cette commande.")

    @app_commands.command(name="lynkr", description="Traduit en Lynkr, un texte écrit en Commun")
    @app_commands.guild_only()
    async def lynkr_slash(self, interaction: discord.Interaction, texte: str) -> None:
        """

        :param interaction:
        :param texte:
        """
        await interaction.response.defer(ephemeral=True)
        member = interaction.user
        role = get(member.guild.roles, name="Codex")
        if member in role.members:
            doc, synonymable = pretranslation_commun_to_lynkr(texte)
            embed = discord.Embed(title="TRADUCTION : Commun → Lynkr",
                                  url="https://www.herobrine.fr/index.php?p=codex",
                                  description=texte,
                                  color=discord.Color.dark_gold())
            if len(synonymable) > 0:
                embed.add_field(name="Traduction",
                                value="",
                                inline=False)
                embed.add_field(name="Synonymes",
                                value="",
                                inline=False)
            else:
                ...
            await interaction.followup.send(embed=embed, view=SynonymView(doc, synonymable))
        else:
            await interaction.followup.send(f"Il te faut le rôle {role.mention} pour utiliser cette commande.")


async def setup(bot: commands.Bot) -> None:
    """

    :param bot:
    """
    await bot.add_cog(Lynkr(bot))
