import os
from pypdf import PdfReader
from datetime import datetime

def charger_pdf(chemin_pdf: str) -> list[dict]:
    """ 
    Lit un fichier PDF et extrait le texte page par page avec ses métadonnées.
    
    Args:
        chemin_pdf (str): Le chemin vers le fichier PDF.
        
    Returns:
        list[dict]: Une liste de dictionnaires contenant le texte et les métadonnées.
    """
    
    if not os.path.exists(chemin_pdf):
        raise FileNotFoundError(f"Le fichier {chemin_pdf} n'existe pas.")

    lecteur = PdfReader(chemin_pdf)
    nom_fichier = os.path.basename(chemin_pdf)
    pages_extraites = []

    for index, page in enumerate(lecteur.pages):
        texte_page = page.extract_text()
        if texte_page and texte_page.strip():
            pages_extraites.append({
                "page_number": index + 1,
                "text": texte_page.strip(),
                "source": nom_fichier
            })

    return pages_extraites

def decouper_texte(pages: list[dict], taille_chunk: int = 500, chevauchement: int = 50) -> list[dict]:
    """
    Découpe le texte extrait des pages en morceaux (chunks) de taille spécifiée avec un chevauchement donné. 
    Args:
        pages (list[dict]): Liste de dictionnaires contenant le texte et les métadonnées des pages.
        taille_chunk (int): Nombre de mots par chunk.
        chevauchement (int): Nombre de mots qui se chevauchent entre les chunks.
    Returns:
        list[dict]: Une liste de dictionnaires contenant les chunks de texte et leurs métadonnées.
    """

    chunks = []
    chunk_id = 0

    horodatage = datetime.now().strftime("%Y%m%d_%H%M%S")

    for page in pages:
        mots = page["text"].split()

        pas = taille_chunk - chevauchement

        for i in range(0, len(mots), pas):
            sous_liste_mots = mots[i:i + taille_chunk]
            morceau = " ".join(sous_liste_mots)

            if morceau.strip():
                chunk_id += 1

                id_unique = f"{page['source']}_{horodatage}_chunk_{chunk_id}"

                chunks.append({
                    "id": id_unique,
                    "text": morceau,
                    "metadata": {
                        "source": page["source"],
                        "page": page["page_number"],
                        "total_mots": len(morceau.split())
                    }
                })

    return chunks