import streamlit as st
from langchain.document_loaders import PyPDFLoader, CSVLoader
from langchain.vectorstores import Chroma
from langchain.embeddings.openai import OpenAIEmbeddings
from langchain.chains import RetrievalQA
from langchain.llms import OpenAI
from dotenv import load_dotenv
import os
import uuid
from pathlib import Path

# Load environment variables
load_dotenv()

# Initialize OpenAI and ChromaDB
openai_api_key = os.getenv("OPENAI_API_KEY")
persist_directory = ".chromadb"

# LangChain Components
embeddings = OpenAIEmbeddings(openai_api_key=openai_api_key)
vector_store = Chroma(persist_directory=persist_directory,
                      embedding_function=embeddings)
retriever = vector_store.as_retriever()
qa_chain = RetrievalQA.from_chain_type(
    llm=OpenAI(model_kwargs={
               "model": "gpt-3.5-turbo-instruct"}, openai_api_key=openai_api_key),
    retriever=retriever,
    return_source_documents=True  # Ensure source documents are included
)

# Directory to store uploaded files
UPLOAD_DIR = Path.cwd() / "uploaded_files"
UPLOAD_DIR.mkdir(exist_ok=True)

# Initialize session state
if "uploaded_files" not in st.session_state:
    st.session_state.uploaded_files = []
if "cited_files" not in st.session_state:
    st.session_state.cited_files = set()

# Helper functions


def process_pdf(file, file_name):
    """Processes a PDF file using LangChain's PyPDFLoader."""
    file_path = UPLOAD_DIR / file_name
    with open(file_path, "wb") as tmp_file:
        tmp_file.write(file.read())
    loader = PyPDFLoader(str(file_path))
    documents = loader.load()
    for doc in documents:
        doc.metadata["source"] = str(file_path)

    return documents


def process_csv(file, file_name):
    """Processes a CSV file using LangChain's CSVLoader."""
    file_path = UPLOAD_DIR / file_name
    with open(file_path, "wb") as tmp_file:
        tmp_file.write(file.read())
    loader = CSVLoader(file_path=str(file_path))
    documents = loader.load()
    for doc in documents:
        doc.metadata["source"] = str(file_path)
    return documents


def save_to_vector_store(documents):
    """Saves documents to the vector store."""
    # Ensure unique IDs for each document
    ids = [str(uuid.uuid4()) for _ in documents]
    vector_store.add_documents(documents, ids=ids)
    vector_store.persist()
    st.write("Documents successfully added to the vector store.")


def get_file_download_button(file_path, unique_key):
    """Generates a Streamlit download button for a file with a unique key."""
    file_name = Path(file_path).name
    with open(file_path, "rb") as file:
        file_data = file.read()
    st.download_button(
        label=f"Download {file_name}",
        data=file_data,
        file_name=file_name,
        mime="application/octet-stream",
        key=f"download-{uuid.uuid1()}"  # Unique key for each button
    )


# Streamlit App UI
st.title("QA with Your Documents")

# File Upload
uploaded_files = st.file_uploader(
    "Upload PDF or CSV files", type=["pdf", "csv"], accept_multiple_files=True)

if uploaded_files:
    all_documents = []
    for uploaded_file in uploaded_files:
        file_name = uploaded_file.name
        file_extension = file_name.split(".")[-1]

        # Process the file based on extension
        if file_extension == "pdf":
            documents = process_pdf(uploaded_file, file_name)
        elif file_extension == "csv":
            documents = process_csv(uploaded_file, file_name)
        else:
            st.error(f"Unsupported file format: {file_extension}")
            continue

        all_documents.extend(documents)

    # Save documents to vector store
    if all_documents:
        save_to_vector_store(all_documents)
        st.success(
            "All files have been uploaded and stored in the vector database.")

# Chat Section
st.header("Chat with Your Documents")
query = st.text_input("Ask a question about the uploaded documents:")

if st.button("Submit Query") and query:
    try:
        result = qa_chain({"query": query})
        answer = result["result"]
        sources = result.get("source_documents", [])

        st.write(f"**Answer:** {answer}")

        if sources:
            # Update session state for cited files
            cited_files = {Path(doc.metadata.get(
                "source", "")).name for doc in sources}
            st.session_state.cited_files.clear()
            st.session_state.cited_files.update(cited_files)

            # Display cited files for download
            st.write("### Cited Files:")
            for file_name in st.session_state.cited_files:
                file_path = UPLOAD_DIR / file_name
                if file_path.exists():
                    get_file_download_button(file_path, file_name)
        else:
            st.write("No sources available.")
    except Exception as e:
        st.error(f"Error: {e}")
