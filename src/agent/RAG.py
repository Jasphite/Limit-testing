from typing import TypedDict, List, Dict
from typing_extensions import Annotated
from langchain_core.documents import Document
from langgraph.graph import StateGraph, END
from langchain_openai import ChatOpenAI
from langchain_community.vectorstores import FAISS
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import UnstructuredFileLoader, DirectoryLoader
from langchain_unstructured import UnstructuredLoader
from dotenv import load_dotenv
from langchain_openai import OpenAIEmbeddings
from langchain_core.prompts import ChatPromptTemplate
from langchain.chains import RetrievalQA
import csv
import os
from pathlib import Path

load_dotenv()
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

CSV_FILE = "summary_application.csv"

class Appstate(TypedDict):
    documents: List[Document]
    classified_docs: Dict[str, Document]
    summary: str
    missing: List[str]
    confirmed: bool
    submitted: bool
    annual_budget: str 

def ask_budget_node(state: Appstate) -> Appstate:
    print("How much are you willing to spend annually?")
    budget = input("Your answer: ").strip()
    print(f"You entered: {budget}")
    state["annual_budget"] = budget
    return state

def save_budget_to_csv(state: dict):
    Filebudget = "budget.csv"
    file_exists = os.path.isfile(Filebudget)

    with open(Filebudget, mode="a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["annual_budget"])

        if not file_exists:
            writer.writeheader()

        writer.writerow({
            "annual_budget": state.get("annual_budget", "")
        })

def save_to_csv(state: dict):
    CSV_FILE = "application_summaries.csv"
    file_exists = os.path.isfile(CSV_FILE)

    with open(CSV_FILE, mode="a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["summary", "confirmed", "submitted"])

        if not file_exists:
            writer.writeheader()

        writer.writerow({
            "summary": state.get("summary", ""),
            "confirmed": state.get("confirmed", False),
            "submitted": state.get("submitted", False)
        })

def save(state: Appstate) -> Appstate:
    print("Saving data")

    summary = state.get("summary", "[No summary]")
    confirmed = state.get("confirmed", False)
    submitted = state.get("submitted", False)

    save_to_csv({
        "summary": summary,
        "confirmed": confirmed,
        "submitted": submitted
    })

    print("Save complete.")
    return state

def budget(state: Appstate) -> Appstate:
    return state

def save_budget(state: Appstate) -> Appstate:
    print("Saving Budget")
    budget = state.get("annual_budget", "[No budget provided]")
    if budget == "[No budget provided]":
        print("Warning: No budget provided before save.")
    save_budget_to_csv({
        "annual_budget": budget,
    })
    return state

prompt = ChatPromptTemplate.from_messages([
    ("system", "You are a university agent helping someone. "
               "Your job is to create a detailed summary based on information from the documents. "
               "Be kind, be honest, and don't be biased. "
               "If any key information is missing, list what’s missing."),
    ("user", "Use the following documents to extract:\n"
             "- Academic achievements\n"
             "- Extracurricular activities\n"
             "- Relevant skills and experience\n"
             "- Current place of living\n"
             "- Hobbies and passions\n"
             "- Anything else necessary for a university application\n\n"
             "- Major of choice\n"
             "Documents:\n{context}")
])

doc_loader = DirectoryLoader("your_docs", loader_cls=UnstructuredFileLoader)
raw_docs = doc_loader.load()
print(f"Loaded {len(raw_docs)} raw documents")

splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=100)
split_docs = splitter.split_documents(raw_docs)
print(f"Split into {len(split_docs)} document chunks")

embedding = OpenAIEmbeddings()
vectorstore = FAISS.from_documents(split_docs, embedding)

retriever = vectorstore.as_retriever()
llm = ChatOpenAI(temperature=0)

qa_chain = RetrievalQA.from_chain_type(
    llm=llm,
    retriever=retriever,
    chain_type="stuff",
    chain_type_kwargs={"prompt": prompt}
)

def load_node(state: Appstate) -> Appstate:
    state["documents"] = split_docs
    return state

def summarize_node(state: Appstate) -> Appstate:
    response = qa_chain.invoke("Please extract all relevant info for university application.")
    summary = response["result"]
    state["summary"] = summary
    state["confirmed"] = True  # <-- ADDED
    state["submitted"] = False  # <-- ADDED
    return state

# Build the graph

graph_builder = StateGraph(Appstate)
graph_builder.add_node("load", load_node)
graph_builder.add_node("summarize", summarize_node)
graph_builder.add_node("ask_budget", ask_budget_node)
graph_builder.add_node("saving_budget", save_budget)
graph_builder.add_node("save", save)
graph_builder.set_entry_point("load")
graph_builder.add_edge("load", "summarize")
graph_builder.add_edge("summarize", "ask_budget")
graph_builder.add_edge("ask_budget", "saving_budget")
graph_builder.add_edge("saving_budget", "save")
graph_builder.add_edge("save", END)

# Run it
graph = graph_builder.compile()
final_state = graph.invoke({})
print(final_state["summary"])
