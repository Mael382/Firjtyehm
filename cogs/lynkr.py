from pathlib import Path
import logging
from typing import List, Tuple, Dict, Optional

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
    # Si le token est un adjectif, un nom ou un nom propre, attribuer le tag Lynkr "GRAMNUM" (accord en nombre)
    if token.pos_ in ("ADJ", "NOUN", "PROPN"):
        return "GRAMNUM"
    # Si le token est un auxiliaire ou un verbe, attribuer le tag Lynkr "GRAMCONJ" (conjugaison en temps)
    elif token.pos_ in ("AUX", "VERB"):
        return "GRAMCONJ"
    # Si le token est un numéral, attribuer le tag Lynkr "NUM"
    # Si le token est une ponctuation, attribuer le tag Lynkr "PUNCT"
    elif token.pos_ in ("NUM", "PUNCT"):
        return token.pos_
    # Si le token est une particule de négation "ne" ou "pas", oattribuer le tag Lynkr "PART"
    elif token.pos_ == "ADV" and token.lemma_ in ("ne", "pas"):
        return "PART"
    # Sinon, attribuer le tag Lynkr "X"
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

    # Si le token est un adjectif, rechercher dans le répertoire "adjectif"
    elif token.pos_ == "ADJ":
        directory = "adjectif"
    # Si le token est un nom, rechercher dans le répertoire "substantif"
    elif token.pos_ == "NOUN":
        directory = "substantif"
    # Si le token est un auxiliaire ou un verbe, rechercher dans le répertoire "verbe"
    elif token.pos_ in ("AUX", "VERB"):
        directory = "verbe"
    # Si le token est un adverbe, rechercher dans le répertoire "adverbe"
    elif token.pos_ == "ADV":
        directory = "adverbe"
    # Si le token est une interjection, rechercher dans le répertoire "interjection"
    elif token.pos_ == "INTJ":
        directory = "interjection"
    # Sinon, rechercher dans tous les répertoires
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


# Sous-fonction de la fonction `lynkr_translation_method`
def complete_lynkr_translation_gramnum(token: Token, lynkr: Optional[str] = None) -> Optional[str]:
    """Fonction pour compléter la traduction en Lynkr d'un token avec le tag Lynkr `GRAMNUM`.

    :param token: Le token Spacy pour lequel la traduction en Lynkr doit être complétée.
    :param lynkr: La traduction actuelle du token en Lynkr.
    :return: La traduction complétée du token en Lynkr.
    """
    # Si aucune traduction n'est fournie, utiliser la traduction du lemme du token
    if lynkr is None:
        translation = token._.lynkr_lemma_translation
    else:
        translation = lynkr

    # Si une traduction est disponible :
    if translation is not None:
        # Vérifier si le token est au pluriel et, si sa traduction ne se termine pas déjà par un "s", en ajouter un
        number = token.morph.to_dict()["Number"]
        if (number == "Plur") and (translation[-1] != "s"):
            return f"{translation}s"
        else:
            return translation


# Sous-fonction de la fonction `lynkr_translation_method`
def complete_lynkr_translation_gramconj(token: Token, lynkr: Optional[str] = None) -> Optional[str]:
    """Fonction pour compléter la traduction en Lynkr d'un token avec le tag Lynkr `GRAMCONJ`.

    :param token: Le token Spacy pour lequel la traduction en Lynkr doit être complétée.
    :param lynkr: La traduction actuelle du token en Lynkr.
    :return: La traduction complétée du token en Lynkr.
    """
    # Si aucune traduction n'est fournie, utiliser la traduction du lemme du token
    if lynkr is None:
        translation = token._.lynkr_lemma_translation
    else:
        translation = lynkr

    # Si une traduction est disponible :
    if translation is not None:

        # Déterminer la polarité du verbe en examinant les deux tokens précédents
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

        # Si le verbe n'est ni "mourir" ni "vivre" :
        if token.lemma_ not in ("mourir", "vivre"):

            # Déterminer le temps du verbe et le conjuguer en conséquence
            tense = token.morph.to_dict()["Tense"]
            if tense == "Pres":
                return f"{polarity}{translation[:-1]}"
            elif tense == "Past":
                return f"{polarity}{translation[:-1]}p"
            elif tense == "Fut":
                return f"{polarity}{translation[:-1]}f"

        return f"{polarity}{translation}"


# Sous-fonction de la fonction `lynkr_translation_method`
def complete_lynkr_translation_x(token: Token, lynkr: Optional[str] = None) -> Optional[str]:
    """Fonction pour compléter la traduction en Lynkr d'un token avec le tag Lynkr `X`.

    :param token: Le token Spacy pour lequel la traduction en Lynkr doit être complétée.
    :param lynkr: La traduction actuelle du token en Lynkr.
    :return: La traduction complétée du token en Lynkr.
    """
    # Si aucune traduction n'est fournie, utiliser la traduction du lemme du token
    if lynkr is None:
        translation = token._.lynkr_lemma_translation
    else:
        translation = lynkr

    # Si une traduction est disponible, la renvoyer
    if translation is not None:
        return translation


# Méthode personnalisée `lynkr_translation` pour les tokens Spacy
def lynkr_translation_method(token: Token, synonym: Optional[str] = None) -> Optional[str]:
    """Fonction pour obtenir la traduction en Lynkr d'un token Spacy.

    :param token: Le token Spacy pour lequel la traduction en Lynkr doit être obtenue.
    :param synonym: Le synonyme à utiliser pour la traduction Lynkr, si nécessaire.
    """
    # Obtenir la traduction du lemme en Lynkr du token
    translation = token._.lynkr_lemma_translation

    # Si le tag Lynkr du token est parmi "GRAMNUM", "GRAMCONJ" ou "X" :
    if token._.lynkr_tag in ("GRAMNUM", "GRAMCONJ", "X"):
        series = LYNKR_SERIES[token._.lynkr_tag]

        # Si aucune traduction n'est disponible pour le token :
        if translation is None:

            # Si un synonyme est fourni et qu'il est traduisible en Lynkr, utiliser sa traduction
            if synonym is not None:
                if synonym in token._.lynkr_compatible_synonyms:
                    translation = series[synonym]
                    token._.lynkr_applied_synonym = synonym

            # Si aucun synonyme n'est fourni, utiliser le meilleur synonyme traduisible en Lynkr, contextuellement
            else:
                if len(token._.lynkr_compatible_synonyms) > 0:
                    best_synonym = max(NLP.pipe(token._.lynkr_compatible_synonyms),
                                       key=lambda x: x.similarity(token.sent.as_doc())).text
                    translation = series[best_synonym]
                    token._.lynkr_applied_synonym = best_synonym

        # Si une traduction est disponible :
        if translation is not None:
            # Compléter la traduction selon le tag Lynkr du token
            if token._.lynkr_tag == "GRAMNUM":
                translation = complete_lynkr_translation_gramnum(token, translation)
            elif token._.lynkr_tag == "GRAMCONJ":
                translation = complete_lynkr_translation_gramconj(token, translation)
            elif token._.lynkr_tag == "X":
                translation = complete_lynkr_translation_x(token, translation)

    return translation


# Application de la méthode `get_lynkr_translation` aux tokens Spacy
Token.set_extension("get_lynkr_translation", method=lynkr_translation_method)


# Sous-fonction des fonctions `translation_commun_to_lynkr_synonym`, `translation_commun_to_lynkr_peut_etre`,
# `translation_commun_to_lynkr_au_revoir` et `translation_commun_to_lynkr_default`
def apply_case_to_lynkr(token: Token, lynkr: str) -> str:
    """Fonction pour appliquer la casse à une traduction en Lynkr d'un token Spacy.

    :param token: Le token Spacy duquel la casse est extraite.
    :param lynkr: La traduction en Lynkr à formater.
    :return: La traduction en Lynkr avec la casse appropriée.
    """
    if token.shape_.islower():
        return lynkr.lower()
    elif token.shape_.istitle():
        return lynkr.title()
    elif token.shape_.isupper():
        return lynkr.upper()
    else:
        return lynkr.capitalize()


# Sous-fonction des fonctions `complete_translation_commun_to_lynkr` et `fast_translation_commun_to_lynkr`
def translation_commun_to_lynkr_synonym(token: Token, synonym: str) -> str:
    """Fonction pour obtenir la traduction en Lynkr formatée d'un token Spacy, à partir d'un synonyme spécifié.

    :param token: Le token Spacy pour lequel la traduction en Lynkr formatée doit être obtenue.
    :param synonym: Le synonyme à utiliser pour la traduction en Lynkr.
    :return: La traduction en Lynkr formatée du token.
    """
    return apply_case_to_lynkr(token, token._.get_lynkr_translation(synonym))


# Sous-fonction des fonctions `complete_translation_commun_to_lynkr` et `fast_translation_commun_to_lynkr`
def translation_commun_to_lynkr_none(token: Token) -> str:
    """Fonction pour obtenir la traduction en Lynkr formatée d'un token Spacy, s'il n'est pas traduisible.

    :param token: Le token Spacy pour lequel la traduction en Lynkr formatée doit être obtenue.
    :return: La traduction en Lynkr formatée du token.
    """
    return f"`{token.text}`"


# Sous-fonction des fonctions `complete_translation_commun_to_lynkr` et `fast_translation_commun_to_lynkr`
def translation_commun_to_lynkr_empty() -> str:
    """Fonction pour obtenir la traduction en Lynkr formatée d'un token Spacy, si elle est vide.

    :return: La traduction en Lynkr formatée du token.
    """
    return ""


# Sous-fonction des fonctions `complete_translation_commun_to_lynkr` et `fast_translation_commun_to_lynkr`
def translation_commun_to_lynkr_peut_etre(token: Token) -> str:
    """Fonction pour obtenir la traduction en Lynkr formatée de l'expression "peut-être".

    :param token: Le token Spacy source.
    :return: La traduction en Lynkr formatée de l'expression "peut-être".
    """
    return apply_case_to_lynkr(token.nbor(-2), "pyeséa")


# Sous-fonction des fonctions `complete_translation_commun_to_lynkr` et `fast_translation_commun_to_lynkr`
def translation_commun_to_lynkr_au_revoir(token: Token) -> Tuple[str, str]:
    """Fonction pour obtenir la traduction en Lynkr formatée de l'expression "au revoir".

    :param token: Le token Spacy source.
    :return: La traduction en Lynkr formatée de l'expression "au revoir".
    """
    return apply_case_to_lynkr(token.nbor(-1), "paers"), apply_case_to_lynkr(token, "esperita")  # Ajouter
    # la réponse variante "paers amars"


# Sous-fonction des fonctions `complete_translation_commun_to_lynkr` et `fast_translation_commun_to_lynkr`
def translation_commun_to_lynkr_default(token: Token) -> str:
    """

    :param token: Le token Spacy pour lequel la traduction en Lynkr formatée doit être obtenue.
    :return: La traduction en Lynkr formatée du token.
    """
    return apply_case_to_lynkr(token, token._.get_lynkr_translation())


# Sous-fonction des fonctions `complete_translation_commun_to_lynkr` et `fast_translation_commun_to_lynkr`
def translation_to_text(translation: List[str]) -> str:
    """Fonction pour récupérer la traduction complète en Lynkr sous forme de texte.

    :param translation: La traduction complète en Lynkr à convertir en texte.
    :return: Le texte correspondant à la traduction complète en Lynkr.
    """
    text = [translation[0]]

    # Parcourir chaque mot dans la traduction :
    if len(translation) > 1:
        for word in translation[1:]:

            # Ajouter un espace, s'il n'y a pas de caractère spécial ouvrant avant
            if (word not in ('"', ")", ",", "-", ".", "]", "}")) and (text[-1] not in ('"', "(", "-", "]", "}")):
                text.append(" ")

            # Ajouter un espace, si c'est un guillemet ouvrant
            elif word == '"' and text.count('"') % 2 == 0:
                text.append(" ")

            # Ajouter un espace, s'il y a un guillemet fermant avant
            elif (word not in (")", ",", "-", ".", "]", "}")) and (text[-1] == '"') and (text.count('"') % 2 == 0):
                text.append(" ")

            # Ajouter le mot
            text.append(word)

    return "".join(text)


def pretranslation_commun_to_lynkr(text: str) -> Tuple[Doc, Tuple[int, ...] | Tuple]:
    """Fonction pour préparer le texte à la traduction en Lynkr en identifiant les tokens nécessitant un synonyme.

    :param text: Le texte source à traduire en Lynkr.
    :return: Un tuple contenant le doc Spacy du texte et les indices des tokens nécessitant un synonyme.
    """
    doc = NLP(text)
    synonymable = []

    # Parcourir chaque token dans le document Spacy :
    for i, token in enumerate(doc):
        # Si le token n'a pas de traduction en Lynkr mais a des synonymes compatibles avec Lynkr, récupérer son indice
        if token._.lynkr_lemma_translation is None and len(token._.lynkr_compatible_synonyms) > 0:
            synonymable.append(i)

    return doc, tuple(synonymable)


def complete_translation_commun_to_lynkr(doc: Doc, synonyms: Optional[Dict[int, str]] = None) ->\
        Tuple[str, Tuple[Token, ...], Tuple[Tuple[str, str], ...]]:
    """Fonction pour achever la traduction en Lynkr du texte en utilisant les synonymes spécifiés.

    :param doc: Le doc Spacy du texte source.
    :param synonyms: Un dictionnaire contenant les indices des tokens nécessitant un synonyme et leur synonyme associé.
    :return: Un tuple contenant la traduction complète en Lynkr, les tokens non traduits et les paires (mot, synonyme)
        utilisées.
    """
    if synonyms is not None:
        synonyms_keys = frozenset(synonyms.keys())
    else:
        synonyms_keys = frozenset()
    translation, untranslated, synonymed = [], [], []

    # Parcourir chaque token et son indice dans le doc Spacy :
    for i, token in enumerate(doc):

        # Si le token a un synonyme spécifié pour la traduction :
        if i in synonyms_keys:
            # Traduire le synonyme et récupérer la traduction
            translation.append(translation_commun_to_lynkr_synonym(token, synonyms[i]))
            # Récupérer la paire (mot, synonyme)
            synonymed.append((token.lemma_, token._.lynkr_applied_synonym))

        # Si le token n'a pas de traduction en Lynkr :
        elif token._.lynkr_lemma_translation is None:
            # Récupérer le token tel quel pour la traduction
            translation.append(translation_commun_to_lynkr_none(token))
            # Récupérer le token non traduit
            untranslated.append(token)

        # Si le lemme du token a une traduction vide en Lynkr, récupérer la traduction vide
        elif token._.lynkr_lemma_translation == "":
            translation.append(translation_commun_to_lynkr_empty())

        # Si l'expression est "peut-être", modifier la traduction en conséquence
        elif i > 2 and token.lower_ == "être" and token.nbor(-1).text == "-" and token.nbor(-2).lower_ == "peut":
            translation.pop()
            translation.pop()
            translation.append(translation_commun_to_lynkr_peut_etre(token))

        # Si l'expression est "au revoir", modifier la traduction en conséquence
        elif i > 1 and token.lower_ == "revoir" and token.nbor(-1).lower_ == "au":
            translation.pop()
            translation.extend(translation_commun_to_lynkr_au_revoir(token))

        # Sinon, utiliser la traduction par défaut
        else:
            translation.append(translation_commun_to_lynkr_default(token))

    return translation_to_text(translation), tuple(untranslated), tuple(synonymed)


def fast_translation_commun_to_lynkr(text: str) -> Tuple[str, Tuple[Token, ...], Tuple[Tuple[str, str], ...]]:
    """Fonction pour traduire le texte en Lynkr directement, en utilisant les meilleurs synonymes contextuels.

    :param text: Le texte source à traduire en Lynkr.
    :return: Un tuple contenant la traduction complète en Lynkr, les tokens non traduits et les paires (mot, synonyme)
        utilisées.
    """
    doc = NLP(text)
    translation, untranslated, synonymed = [], [], []

    # Parcourir chaque token et son indice dans le doc Spacy :
    for i, token in enumerate(doc):

        # Si le token n'a pas de traduction en Lynkr mais a des synonymes traduisibles :
        if token._.lynkr_lemma_translation is None and len(token._.lynkr_compatible_synonyms) > 0:
            # Traduire le synonyme et récupérer la traduction
            translation.append(translation_commun_to_lynkr_default(token))
            # Récupérer la paire (mot, synonyme)
            synonymed.append((token.lemma_, token._.lynkr_applied_synonym))

        # Si le token n'a pas de traduction en Lynkr :
        elif token._.lynkr_lemma_translation is None:
            translation.append(translation_commun_to_lynkr_none(token))
            # Récupérer le token tel quel pour la traduction
            untranslated.append(token)
            # Récupérer le token non traduit

        # Si le lemme du token a une traduction vide en Lynkr, récupérer la traduction vide
        elif token._.lynkr_lemma_translation == "":
            translation.append(translation_commun_to_lynkr_empty())

        # Si l'expression est "peut-être", modifier la traduction en conséquence
        elif i > 2 and token.lower_ == "être" and token.nbor(-1).text == "-" and token.nbor(-2).lower_ == "peut":
            translation.pop()
            translation.pop()
            translation.append(translation_commun_to_lynkr_peut_etre(token))

        # Si l'expression est "au revoir", modifier la traduction en conséquence
        elif i > 1 and token.lower_ == "revoir" and token.nbor(-1).lower_ == "au":
            translation.pop()
            translation.extend(translation_commun_to_lynkr_au_revoir(token))

        # Sinon, utiliser la traduction par défaut
        else:
            translation.append(translation_commun_to_lynkr_default(token))

    return translation_to_text(translation), tuple(untranslated), tuple(synonymed)


# Sous-classe pour la classe `SynonymView`
class SynonymSelect(ui.Select):
    """Classe représentant un sélecteur de synonymes pour un mot donné dans le texte à traduire.

    Ce composant permet à l'utilisateur de choisir parmi une liste de synonymes pour un mot spécifique dans le texte à
    traduire.

    :param index: Indice du mot dans le doc Spacy pour lequel le synonyme doit être choisi actuellement.
    :type index: int
    :param doc: Le doc Spacy contenant le texte à traduire.
    :type doc: Doc
    :param synonymable: Un tuple contenant les indices des mots dans le doc Spacy pour lesquels des synonymes doivent
        être choisis.
    :type synonymable: Tuple[int, ...]
    :param selected_synonyms: Liste des synonymes choisis actuellement.
    :type selected_synonyms: List[str]
    """

    def __init__(self, doc: Doc, synonymable: Tuple[int, ...]) -> None:
        """Initialise un nouveau sélecteur de synonymes.

        :param doc: Le doc Spacy contenant le texte à traduire.
        :param synonymable: Un tuple contenant les indices des mots dans le doc Spacy pour lesquels des synonymes
            doivent être choisis.
        """
        # Placeholder du menu déroulant
        placeholder = f'Choisissez un synonyme pour "{doc[synonymable[0]].text}" !'

        # Options du menu déroulant
        options = []
        for synonym in doc[synonymable[0]]._.lynkr_compatible_synonyms:
            # Options de synonymes
            options.append(SelectOption(label=f'"{synonym}"',
                                        value=synonym))
        # Option sans synonyme
        options.append(SelectOption(label="Aucun synonyme",
                                    value="None",
                                    description=f'Attention : "{doc[synonymable[0]].lemma_}" ne sera pas traduit !'))

        super().__init__(placeholder=placeholder, options=options)
        self.index = 0
        self.doc = doc
        self.synonymable = synonymable
        self.selected_synonyms = []

    async def callback(self, interaction: Interaction) -> None:
        """Méthode de rappel exécutée lorsqu'une interaction avec le menu déroulant se produit.

        :param interaction: L'interaction avec le menu déroulant.
        """
        await interaction.response.defer()


# Sous-classe pour la classe `SynonymView`
class SynonymButton(ui.Button):
    """Une classe représentant un bouton pour valider la sélection de synonymes.

    :param select: Le sélecteur de synonymes associé au bouton.
    :type select: SynonymSelect
    :param translation: La traduction du texte.
    :type translation: str
    """

    def __init__(self, select: SynonymSelect) -> None:
        """Initialise une instance de SynonymButton.

        :param select: Le sélecteur de synonymes associé au bouton.
        """
        super().__init__(label="Valider", style=discord.ButtonStyle.blurple)
        self.select = select
        self.translation = ""

    async def callback(self, interaction: Interaction) -> None:
        """Méthode de rappel exécutée lorsqu'une interaction avec le bouton se produit.

        :param interaction: L'interaction avec le bouton.
        """
        # Sauvegarder le synonyme sélectionné et passer au suivant
        self.select.index += 1
        self.select.selected_synonyms.append(self.select.values[0])

        # Si le synonyme suivant existe :
        if self.select.index < len(self.select.synonymable):

            # Appliquer un nouveau placeholder au menu déroulant
            placeholder = f'Choisissez un synonyme pour "{self.select.doc[self.select.synonymable[self.select.index]].text}" !'
            self.select.placeholder = placeholder

            # Appliquer de nouvelles options au menu déroulant
            options = []
            for synonym in self.select.doc[self.select.synonymable[self.select.index]]._.lynkr_compatible_synonyms:
                options.append(SelectOption(label=f'"{synonym}"',
                                            value=synonym))
            options.append(SelectOption(label="Aucun synonyme",
                                        value="None",
                                        description=f'Attention : "{self.select.doc[self.select.synonymable[self.select.index]].lemma_}" ne sera pas traduit !'))
            self.select.options = options

        # Sinon :
        else:
            # Désactiver les composants d'interaction
            self.select.disabled = True
            self.disabled = True

            # Générer la traduction et le tuple des tokens intraduisibles
            translation, untranslated, _ = complete_translation_commun_to_lynkr(self.select.doc, dict(
                zip(self.select.synonymable, self.select.selected_synonyms)))

            # Appliquer la nouvelle traduction au bouton
            self.translation = translation

            # Décomposer les tokens intraduisibles et les sauvegarder dans le csv mémoire
            text, lemma, pos, morph = [], [], [], []
            for token in untranslated:
                text.append(token.text)
                lemma.append(token.lemma_)
                pos.append(token.pos_)
                morph.append(token.morph)
            df = pd.DataFrame({"text": text, "lemma": lemma, "pos": pos, "morph": morph})
            df.to_csv(MEMORY_PATH, header=False, index=False, mode="a")

        # Intégrer le texte original, la traduction et les paires (mot, synonyme) à chaque étape
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

        # Envoyer l'intégration
        await interaction.response.edit_message(embed=embed, view=self.view)


class SynonymView(ui.View):
    """Une classe représentant une vue contenant à la fois un menu déroulant et un bouton pour la sélection de
    synonymes.
    """

    def __init__(self, doc: Doc, synonymable: Tuple[int, ...]) -> None:
        """Initialise une instance de SynonymView.

        :param doc: Le doc Spacy contenant le texte à traduire.
        :param synonymable: Un tuple contenant les indices des mots dans le doc Spacy pour lesquels des synonymes
            doivent être choisis.
        """
        super().__init__(timeout=None)

        # Créer une instance de SynonymSelect et de SynonymButton
        select = SynonymSelect(doc, synonymable)
        button = SynonymButton(select)

        # Ajouter le menu déroulant et le bouton à la vue
        self.add_item(select)
        self.add_item(button)


# Cog `Lynkr`
class Lynkr(commands.Cog):
    """Une cog Discord.py pour traduire des textes de la langue Commun en Lynkr sur Discord.

    :param bot: Le bot Discord associé à cette cog.
    :type bot: commands.Bot
    """

    def __init__(self, bot: commands.Bot) -> None:
        """Initialise la cog avec le bot Discord associé.

        :param bot: Le bot Discord associé à cette cog.
        """
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        """Un écouteur d'événements qui est déclenché lorsque le bot est prêt."""
        print("Lynkr cog loaded")

    @app_commands.command(name="lynkr", description="Traduit en Lynkr, un texte écrit en Commun")
    @app_commands.guild_only()
    async def lynkr_slash(self, interaction: discord.Interaction, texte: str) -> None:
        """Une commande slash pour traduire en Lynkr un texte en Commun.

        :param interaction: L'interaction Discord pour la commande.
        :param texte: Le texte à traduire en Lynkr.
        """
        await interaction.response.defer(ephemeral=True)
        member = interaction.user
        role = get(member.guild.roles, name="Codex")

        # Si l'utilisateur a le rôle `Codex` :
        if member in role.members:

            # Générer le doc Spacy du texte et les indices des tokens nécessitant un synonyme.
            doc, synonymable = pretranslation_commun_to_lynkr(texte)

            # Intégrer le texte original
            embed = discord.Embed(title="TRADUCTION : Commun → Lynkr",
                                  url="https://www.herobrine.fr/index.php?p=codex",
                                  description=texte,
                                  color=discord.Color.dark_gold())

            # S'il y a des paires (mot, synonyme) :
            if len(synonymable) > 0:

                # Intégrer la traduction vide et les paires (mot, synonyme) vides
                embed.add_field(name="Traduction",
                                value="",
                                inline=False)
                embed.add_field(name="Synonymes",
                                value="",
                                inline=False)

                # Envoyer l'intégration
                await interaction.followup.send(embed=embed, view=SynonymView(doc, synonymable))

            # Sinon :
            else:

                # Générer la traduction et le tuple des tokens intraduisibles
                translation, untranslated, _ = complete_translation_commun_to_lynkr(doc)

                # Intégrer la traduction
                embed.add_field(name="Traduction",
                                value=translation,
                                inline=False)

                # Envoyer l'intégration
                await interaction.followup.send(embed=embed)

                # Décomposer les tokens intraduisibles et les sauvegarder dans le csv mémoire
                text, lemma, pos, morph = [], [], [], []
                for token in untranslated:
                    text.append(token.text)
                    lemma.append(token.lemma_)
                    pos.append(token.pos_)
                    morph.append(token.morph)
                df = pd.DataFrame({"text": text, "lemma": lemma, "pos": pos, "morph": morph})
                df.to_csv(MEMORY_PATH, header=False, index=False, mode="a")

        # Sinon :
        else:
            await interaction.followup.send(f"Il te faut le rôle {role.mention} pour utiliser cette commande.")

    @app_commands.command(name="fastlynkr", description="Traduit en Lynkr, un texte écrit en Commun")
    @app_commands.guild_only()
    async def fast_lynkr_slash(self, interaction: discord.Interaction, texte: str) -> None:
        """Une commande slash pour traduire en Lynkr rapidement un texte en Commun.

        :param interaction: L'interaction Discord pour la commande.
        :param texte: Le texte à traduire en Lynkr.
        """
        await interaction.response.defer(ephemeral=True)
        member = interaction.user
        role = get(member.guild.roles, name="Codex")

        # Si l'utilisateur a le rôle `Codex` :
        if member in role.members:

            # Générer la traduction, le tuple des tokens intraduisibles et les paires (mot, synonyme) utilisées
            translation, untranslated, synonymed = fast_translation_commun_to_lynkr(texte)

            # Intégrer le texte original et la traduction
            embed = discord.Embed(title="TRADUCTION : Commun → Lynkr",
                                  url="https://www.herobrine.fr/index.php?p=codex",
                                  description=texte,
                                  color=discord.Color.dark_gold())
            embed.add_field(name="Traduction",
                            value=translation,
                            inline=False)

            # S'il y a des paires (mot, synonyme), les intégrer
            if len(synonymed) > 0:
                embed.add_field(name="Synonymes",
                                value="\n".join([f"{synonym[0]} → {synonym[1]}" for synonym in synonymed]),
                                inline=False)

            # Envoyer l'intégration
            await interaction.followup.send(embed=embed)

            # Décomposer les tokens intraduisibles et les sauvegarder dans le csv mémoire
            text, lemma, pos, morph = [], [], [], []
            for token in untranslated:
                text.append(token.text)
                lemma.append(token.lemma_)
                pos.append(token.pos_)
                morph.append(token.morph)
            df = pd.DataFrame({"text": text, "lemma": lemma, "pos": pos, "morph": morph})
            df.to_csv(MEMORY_PATH, header=False, index=False, mode="a")

        # Sinon :
        else:
            await interaction.followup.send(f"Il te faut le rôle {role.mention} pour utiliser cette commande.")


# Configuration de la cog
async def setup(bot: commands.Bot) -> None:
    """Configure la cog Lynkr et l'ajoute au bot Discord.

    :param bot: Le bot Discord auquel ajouter la cog.
    """
    await bot.add_cog(Lynkr(bot))
