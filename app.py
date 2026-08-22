import os
import uuid
import streamlit as st
from src.document_loader import ProcesseurDocuments
from src.vector_store import GestionnaireVecteurs
from src.rag_engine import MoteurRAG
from src.feedback_logger import GestionnaireFeedback
from src.admin_metrics import AnalyseurFeedback

# Configuration de la page Streamlit
st.set_page_config(
    page_title="Chatbot RAG d'Entreprise",
    page_icon="🤖",
    layout="wide"
)

# Mot de passe admin : à définir via une variable d'environnement en production
# (ex: export ADMIN_PASSWORD="..." avant de lancer streamlit)
MOT_DE_PASSE_ADMIN = os.environ.get("ADMIN_PASSWORD", "admin123")

# --- INITIALISATION DES COMPOSANTS ---
@st.cache_resource
def initialiser_rag():
    db = GestionnaireVecteurs()
    rag = MoteurRAG(gestionnaire_db=db)
    logger_feedback = GestionnaireFeedback()
    analyseur_feedback = AnalyseurFeedback()
    return db, rag, logger_feedback, analyseur_feedback

db, rag, logger_feedback, analyseur_feedback = initialiser_rag()

# --- ÉTAT DE SESSION : navigation admin ---
if "admin_authentifie" not in st.session_state:
    st.session_state.admin_authentifie = False
if "afficher_login_admin" not in st.session_state:
    st.session_state.afficher_login_admin = False

# --- BARRE LATÉRALE : GESTION DES DOCUMENTS ---
st.sidebar.header("📁 Base de Connaissances")
dossier_documents = "./data/raw"
os.makedirs(dossier_documents, exist_ok=True)

fichiers_existants = os.listdir(dossier_documents)
st.sidebar.text("Documents actuellement présents :")
if fichiers_existants:
    for f in fichiers_existants:
        st.sidebar.text(f" - {f}")
else:
    st.sidebar.info("Aucun document dans data/raw pour l'instant.")

st.sidebar.caption(f"📊 {db.collection.count()} chunk(s) actuellement indexé(s) dans la base vectorielle.")


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

# --- ACCÈS ADMIN CACHÉ, juste sous le bouton "Indexer" ---
if not st.session_state.admin_authentifie:
    if st.sidebar.button("⚙️", key="btn_admin_toggle", help="Accès administrateur"):
        st.session_state.afficher_login_admin = not st.session_state.afficher_login_admin

    if st.session_state.afficher_login_admin:
        mdp_saisi = st.sidebar.text_input(
            "Mot de passe admin", type="password", key="mdp_admin"
        )
        if st.sidebar.button("Valider", key="btn_valider_admin"):
            if mdp_saisi == MOT_DE_PASSE_ADMIN:
                st.session_state.admin_authentifie = True
                st.session_state.afficher_login_admin = False
                st.rerun()
            else:
                st.sidebar.error("Mot de passe incorrect.")
else:
    # Le même bouton se transforme en bouton de retour vers l'espace utilisateur
    if st.sidebar.button("⬅️ Retour espace utilisateur", key="btn_retour_user"):
        st.session_state.admin_authentifie = False
        st.rerun()


# ============================================================
#  VUE ADMIN
# ============================================================
if st.session_state.admin_authentifie:
    st.title("📊 Tableau de Bord Admin")
    st.subheader("📈 Performance & Retours Utilisateurs")

    mois_dispos = analyseur_feedback.lister_mois_disponibles()

    if not mois_dispos:
        st.info("Aucun log de feedback disponible pour le moment.")
    else:
        mois_selectionne = st.selectbox("Sélectionner la période :", mois_dispos)
        df_logs = analyseur_feedback.charger_donnees_mois(mois_selectionne)
        kpi = analyseur_feedback.calculer_indicateurs(df_logs)

        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Questions Totales", kpi["total_questions"])
        c2.metric("Satisfaction", f"{kpi['taux_satisfaction']} %")
        c3.metric("Pouces 👍", kpi["nb_positifs"])
        c4.metric("Pouces 👎", kpi["nb_negatifs"])
        c5.metric("Sans avis", kpi["nb_sans_avis"])

        st.markdown("---")

        st.write("🔍 **Questions nécessitant une attention (👎) :**")
        df_negatifs = df_logs[df_logs["note_utilisateur"] == "negatif"]
        if not df_negatifs.empty:
            st.dataframe(
                df_negatifs[["date_heure", "question", "reponse", "sources"]],
                width="stretch"
            )
        else:
            st.success("Aucun retour négatif sur cette période.")

        csv_data = df_logs.to_csv(index=False).encode("utf-8")
        st.download_button(
            label="📥 Télécharger le rapport mensuel (CSV)",
            data=csv_data,
            file_name=f"rapport_evaluation_{mois_selectionne}.csv",
            mime="text/csv"
        )

# ============================================================
#  VUE UTILISATEUR (chat)
# ============================================================
else:
    st.title("🤖 Assistant RAG - Base de Connaissances Interne")
    st.markdown("Interroge les documents, guidelines et présentations de l'entreprise en toute sécurité.")

    if "messages" not in st.session_state:
        st.session_state.messages = []

    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

            if message["role"] == "assistant":
                if message.get("sources"):
                    with st.expander("📌 Sources consultées pour cette réponse"):
                        for i, src in enumerate(message["sources"], 1):
                            nom_source = src["metadata"].get("source", "Inconnue")
                            page = src["metadata"].get("page", "Inconnue")
                            st.markdown(f"**Extrait {i}** — Fichier : `{nom_source}` (Page/Slide : {page})")
                            st.caption(f"> {src['texte'][:200]}...")

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

    if question_utilisateur := st.chat_input(
        "Pose ta question sur les documents...", key="chat_input_principal"
    ):
        st.session_state.messages.append({
            "id": str(uuid.uuid4()),
            "role": "user",
            "content": question_utilisateur
        })
        with st.chat_message("user"):
            st.markdown(question_utilisateur)

        with st.chat_message("assistant"):
            with st.spinner("Recherche dans les documents de l'entreprise..."):
                resultat = rag.poser_question(question_utilisateur, top_k=10)
                reponse_texte = resultat["reponse"]
                sources = resultat["sources"]

                st.markdown(reponse_texte)

                if sources:
                    with st.expander("📌 Sources consultées pour cette réponse"):
                        for i, src in enumerate(sources, 1):
                            nom_source = src["metadata"].get("source", "Inconnue")
                            page = src["metadata"].get("page", "Inconnue")
                            st.markdown(f"**Extrait {i}** — Fichier : `{nom_source}` (Page/Slide : {page})")
                            st.caption(f"> {src['texte'][:200]}...")

            st.session_state.messages.append({
                "id": str(uuid.uuid4()),
                "role": "assistant",
                "content": reponse_texte,
                "sources": sources,
                "question_origine": question_utilisateur,
                "feedback": None
            })

        
            logger_feedback.enregistrer_interaction(
                id_interaction=st.session_state.messages[-1]["id"],
                question=question_utilisateur,
                reponse=reponse_texte,
                sources=sources,
                note="sans_avis"
            )

            st.rerun()