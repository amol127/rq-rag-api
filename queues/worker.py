# RQ/queues/worker.py

from dotenv import load_dotenv 
from openai import OpenAI
from langchain_openai import OpenAIEmbeddings
from langchain_qdrant import QdrantVectorStore
import os

load_dotenv()

api_key=os.getenv("OPENROUTER_API_KEY")

openai_client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=api_key,
    default_headers={
        "HTTP-Referer": "http://localhost",
        "X-Title": "Basic RAG"
    }

)

embedding_model =  OpenAIEmbeddings(
    model = "text-embedding-3-large",
    base_url = "https://openrouter.ai/api/v1",
    api_key=api_key
)

vector_db = QdrantVectorStore.from_existing_collection(
    embedding = embedding_model,
    url = "http://localhost:6333",
    collection_name = "learning_rag"
)



def process_query(query:str):
    print("Searching Chunks", query)
    search_query = vector_db.similarity_search(query=query)
    
    context = "\n\n\n".join([f"Page Content : {result.page_content}\nPage Number : {result.metadata['page_label']}\nFile Location: {result.metadata['source']}" for result in search_query])

    SYSTEM_PROMPT = f"""
        you are a helpfull AI Assistance who answer user query based on the available context retrieved from a PDF file along with page_contents and page number.

        you should only ans the user based on the following context and navigation the user to open the right page number to know more.

        Context:{context}
        """
    
    response = openai_client.chat.completions.create(
    model="openai/gpt-4o-mini",
    messages=[
        {"role":"system", "content":SYSTEM_PROMPT},
        {"role":"user", "content":query},
    ]
    )
    
    print(f"AI > ",{response.choices[0].message.content})

    return response.choices[0].message.content





