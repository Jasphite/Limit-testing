import os
import pandas as pd
from dotenv import load_dotenv
from typing import List
from langchain_core.documents import Document
from langchain_core.prompts import ChatPromptTemplate
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_community.vectorstores import FAISS
from langchain.chains.llm import LLMChain
from langchain.chains import StuffDocumentsChain
from langchain.chains import RetrievalQA


load_dotenv()
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE" 


def load_csv(path: str) -> pd.DataFrame:
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        raise ValueError(f" File '{path}' is missing or empty.")
    df = pd.read_csv(path)
    df.columns = df.columns.str.strip()
    df.dropna(inplace=True)
    return df

df_affordable = load_csv("affordable_universities.csv")
df_application = load_csv("application_summaries.csv")


def df_to_documents(df: pd.DataFrame, source_name: str) -> List[Document]:
    docs = []
    for _, row in df.iterrows():
        content = "\n".join([f"{col}: {row[col]}" for col in df.columns])
        docs.append(Document(page_content=f"Source: {source_name}\n{content}"))
    return docs

docs = df_to_documents(df_affordable, "Affordable Universities") + df_to_documents(df_application, "Application Summary")


prompt = ChatPromptTemplate.from_messages([
    ("system", 
     "You are a helpful and honest university advisor. "
     "Your task is to pick the best 10–20 universities from the provided data. "
     "Compare each university's total cost, type, and any other available information. "
     "For each one, give:\n"
     "- A reason for selecting it\n"
     "- Pros and cons\n"
     "- A rating\n"
     "- A clearly labeled section (e.g. === University Name ===)"),
    ("user", "{input_documents}")
])


splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=100)
split_docs = splitter.split_documents(docs)

embedding = OpenAIEmbeddings()
vectorstore = FAISS.from_documents(split_docs, embedding)
retriever = vectorstore.as_retriever()

llm = ChatOpenAI(model="gpt-4-1106-preview", temperature=0)


llm_chain = LLMChain(llm=llm, prompt=prompt)
combine_docs_chain = StuffDocumentsChain(llm_chain=llm_chain, document_variable_name="input_documents")
qa_chain = RetrievalQA(retriever=retriever, combine_documents_chain=combine_docs_chain)

response = qa_chain.invoke({"query": "Please pick the top 10–20 universities from the documents."})
print(response["result"])
