import os
import uuid
import streamlit as st
from src.document_loader import ProcesseurDocuments
from src.vector_store import GestionnaireVecteurs
from src.rag_engine import MoteurRAG
from src.feedback_logger import GestionnaireFeedback

# Configuration de la page Streamlit
st.set_page_config(
    page_title="Chatbot RAG d'Entreprise",
    page_icon="🤖",
    layout="wide"
)

# Titre de l'application
st.title("🤖 Assistant RAG - Base de Connaissances Interne")
st.markdown("Interroge les documents, guidelines et présentations de l'entreprise en toute sécurité.")

# --- INITIALISATION DES COMPOSANTS  ---
@st.cache_resource
def initialiser_rag():
    # 1. On crée d'abord l'instance de la base vectorielle
    db = GestionnaireVecteurs()
    # 2. On passe l'instance 'db' au moteur RAG
    rag = MoteurRAG( gestionnaire_db=db)
    # 3. On initialise le gestionnaire de feedback
    logger_feedback = GestionnaireFeedback()
    
    return db, rag, logger_feedback

# Appel de la fonction
db, rag, logger_feedback = initialiser_rag()

# --- BARRE LATÉRALE : GESTION DES DOCUMENTS ---
st.sidebar.header("📁 Base de Connaissances")
dossier_documents = "./data/raw"

# S'assurer que le dossier existe
os.makedirs(dossier_documents, exist_ok=True)

# Afficher les fichiers déjà présents dans data/raw
fichiers_existants = os.listdir(dossier_documents)
st.sidebar.text("Documents actuellement présents :")
if fichiers_existants:
    for f in fichiers_existants:
        st.sidebar.text(f" - {f}")
else:
    st.sidebar.info("Aucun document dans data/raw pour l'instant.")

# Bouton pour lancer l'indexation de tout le dossier
if st.sidebar.button("🔄 Indexer / Mettre à jour la base"):
    with st.spinner("Ingestion des documents (PDF, Word, Excel, PPTX) en cours..."):
        try:
            processeur = ProcesseurDocuments()
            chunks = processeur.traiter_dossier(dossier_documents)
            if chunks:
                db.ajouter_chunks(chunks)
                st.sidebar.success(f"Succès ! {len(chunks)} chunks indexés.")
            else:
                st.sidebar.warning("Aucun document extractible trouvé.")
        except Exception as e:
            st.sidebar.error(f"Erreur : {str(e)}")

# --- INTERFACE DE CHAT PRINCIPALE ---
st.markdown("---")

# Initialisation de l'historique des messages dans la session Streamlit
if "messages" not in st.session_state:
    st.session_state.messages = []

# Affichage de l'historique des messages
# Affichage de l'historique des messages et des boutons de feedback
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

        # Affichage des sources et des boutons uniquement pour les réponses du bot
        if message["role"] == "assistant":
            if message.get("sources"):
                with st.expander("📌 Sources consultées pour cette réponse"):
                    for i, src in enumerate(message["sources"], 1):
                        nom_source = src["metadata"].get("source", "Inconnue")
                        page = src["metadata"].get("page", "Inconnue")
                        st.markdown(f"**Extrait {i}** — Fichier : `{nom_source}` (Page/Slide : {page})")
                        st.caption(f"> {src['texte'][:200]}...")

            # Boutons de vote 👍 / 👎
            msg_id = message.get("id", "legacy")
            col1, col2, col_info = st.columns([1, 1, 10])

            with col1:
                if st.button("👍", key=f"up_{msg_id}", disabled=(message.get("feedback") == "positif")):
                    message["feedback"] = "positif"
                    logger_feedback.enregistrer_interaction(
                        id_interaction=msg_id,
                        question=message.get("question_origine", ""),
                        reponse=message["content"],
                        sources=message.get("sources", []),
                        note="positif"
                    )
                    st.rerun()

            with col2:
                if st.button("👎", key=f"down_{msg_id}", disabled=(message.get("feedback") == "negatif")):
                    message["feedback"] = "negatif"
                    logger_feedback.enregistrer_interaction(
                        id_interaction=msg_id,
                        question=message.get("question_origine", ""),
                        reponse=message["content"],
                        sources=message.get("sources", []),
                        note="negatif"
                    )
                    st.rerun()

            with col_info:
                if message.get("feedback") == "positif":
                    st.caption("✅ Merci pour votre retour !")
                elif message.get("feedback") == "negatif":
                    st.caption("⚠️ Retour pris en compte.")

# Champ de saisie pour poser une question
if question_utilisateur := st.chat_input("Pose ta question sur les documents..."):
    # 1. Afficher la question de l'utilisateur avec un identifiant unique
    st.session_state.messages.append({
        "id": str(uuid.uuid4()),
        "role": "user",
        "content": question_utilisateur
    })
    with st.chat_message("user"):
        st.markdown(question_utilisateur)

    # 2. Générer la réponse via notre Moteur RAG
    with st.chat_message("assistant"):
        with st.spinner("Recherche dans les documents de l'entreprise..."):
            # Appel de notre méthode RAG
            resultat = rag.poser_question(question_utilisateur, top_k=10)
            reponse_texte = resultat["reponse"]
            sources = resultat["sources"]

            # Affichage de la réponse
            st.markdown(reponse_texte)

            # Affichage des sources utilisées (Transparence et traçabilité pro)
            if sources:
                with st.expander("📌 Sources consultées pour cette réponse"):
                    for i, src in enumerate(sources, 1):
                        nom_source = src["metadata"].get("source", "Inconnue")
                        page = src["metadata"].get("page", "Inconnue")
                        st.markdown(f"**Extrait {i}** — Fichier : `{nom_source}` (Page/Slide : {page})")
                        st.caption(f"> {src['texte'][:200]}...")

        # Sauvegarder la réponse dans l'historique avec métadonnées pour le feedback
        st.session_state.messages.append({
            "id": str(uuid.uuid4()),
            "role": "assistant",
            "content": reponse_texte,
            "sources": sources,
            "question_origine": question_utilisateur,
            "feedback": None
        })
        st.rerun()