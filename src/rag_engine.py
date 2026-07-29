import os
from src.vector_store import GestionnaireVecteurs

# Instruction système d'entreprise (Prompt Template)
SYSTEM_PROMPT = """Tu es un assistant IA d'entreprise expert et rigoureux.
Ton rôle est de répondre à la question de l'utilisateur en t'appuyant EXCLUSIVEMENT sur les documents fournis dans le contexte ci-dessous.

Règles strictes :
1. Si la réponse ne se trouve pas dans le contexte fourni, dis clairement "Je ne trouve pas cette information dans les documents fournis."
2. Ne cherche pas à inventer ou à deviner une réponse basée sur tes connaissances générales.
3. Indique la source et la page du document quand tu donnes une information si cela est pertinent.

Contexte fourni :
{contexte}

Question de l'utilisateur :
{question}

Réponse :"""


class MoteurRAG:
    """
    Moteur RAG (Retrieval-Augmented Generation) principal.

    Description :
        Cette classe orchestre la recherche d'informations dans la base vectorielle
        ChromaDB et la construction du prompt d'entreprise destiné au LLM.

    Attributes:
        gestionnaire_db (GestionnaireVecteurs): L'instance active de la base vectorielle.
    """

    def __init__(self, gestionnaire_db: GestionnaireVecteurs):
        """
        Initialise le moteur RAG avec son gestionnaire vectoriel.

        Args:
            gestionnaire_db (GestionnaireVecteurs): Instance de la base ChromaDB.
        """
        self.db = gestionnaire_db

    def construire_contexte(self, chunks: list[dict]) -> str:
        """
        Formate la liste des chunks trouvés en une seule chaîne de texte lisible.

        Exemple de sortie :
            [Extrait 1 | Source: contrat.pdf, Page: 1]
            Les congés doivent être déposés 2 semaines à l'avance...
            ----------------------------------------
            [Extrait 2 | Source: rh.pdf, Page: 3]
            Le portail RH permet de valider les absences...

        Args:
            chunks (list[dict]): La liste de dictionnaires renvoyée par ChromaDB.

        Returns:
            str: Le bloc de texte représentant l'ensemble des extraits pertinents.
        """
        if not chunks:
            return "Aucun document pertinent trouvé."

        blocs_contexte = []
        for i, chunk in enumerate(chunks, 1):
            source = chunk["metadata"].get("source", "Inconnue")
            page = chunk["metadata"].get("page", "Inconnue")
            texte = chunk["texte"]

            bloc = f"[Extrait {i} | Source: {source}, Page: {page}]\n{texte}"
            blocs_contexte.append(bloc)

        return "\n\n----------------------------------------\n\n".join(blocs_contexte)

    def preparer_prompt(self, question: str, top_k: int = 3) -> dict:
        """
        Interroge ChromaDB pour trouver les chunks pertinents et génère le prompt final.

        Args:
            question (str): La question posée par l'utilisateur.
            top_k (int, optional): Nombre d'extraits à récupérer. Défaut: 3.

        Returns:
            dict: Dictionnaire contenant la question, le contexte extrait et le prompt complet.
        """
        # 1. Recherche des K morceaux les plus pertinents dans ChromaDB
        chunks_pertinents = self.db.chercher_similaires(question, nombre_resultats=top_k)

        # 2. Mise en forme du texte de contexte
        contexte_formate = self.construire_contexte(chunks_pertinents)

        # 3. Injection du contexte et de la question dans notre modèle de prompt
        prompt_final = SYSTEM_PROMPT.format(
            contexte=contexte_formate,
            question=question
        )

        return {
            "question": question,
            "chunks": chunks_pertinents,
            "contexte": contexte_formate,
            "prompt_final": prompt_final
        }