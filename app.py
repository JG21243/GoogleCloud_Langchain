import asyncio
import os
from datetime import datetime
from operator import itemgetter
from typing import List, Optional, Sequence, Tuple, Union
import logging
from uuid import UUID
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from langchain.callbacks.manager import CallbackManagerForRetrieverRun
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_anthropic import ChatAnthropic
from langchain_community.chat_models import ChatVertexAI
from langchain_community.document_loaders import AsyncHtmlLoader
from langchain_community.document_transformers import Html2TextTransformer
from langchain.retrievers.contextual_compression import ContextualCompressionRetriever
from langchain.prompts import ChatPromptTemplate, MessagesPlaceholder, PromptTemplate
from langchain.retrievers import (
    ContextualCompressionRetriever,
    TavilySearchAPIRetriever,
)
from langchain.retrievers.document_compressors import (
    EmbeddingsFilter,
    DocumentCompressorPipeline,
)
from langchain.retrievers.kay import KayAiRetriever
from langchain.retrievers.you import YouRetriever
from langchain.schema import Document
from langchain.schema.language_model import BaseLanguageModel
from langchain.schema.messages import AIMessage, HumanMessage
from langchain.schema.output_parser import StrOutputParser
from langchain.schema.retriever import BaseRetriever
from langchain.schema.runnable import ConfigurableField, Runnable, RunnableBranch, RunnableLambda, RunnableMap
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langsmith import Client

logger = logging.getLogger(__name__)

RESPONSE_TEMPLATE = """\
You are an expert researcher and writer, tasked with answering any question.

Generate a comprehensive and informative, yet concise answer of 1000 words or less for the \
given question based solely on the provided search results (URL and content). You must \
only use information from the provided search results. Use an unbiased and \
objective tone. Combine search results together into a coherent answer. Do not \
repeat text. Cite search results using [{{number}}] notation. Only cite the most \
relevant results that answer the question accurately. Place these citations at the end \
of the sentence or paragraph that reference them - do not put them all at the end. If \
different results refer to different entities within the same name, write separate \
answers for each entity. If you want to cite multiple results for the same sentence, \
format it as `[{{number1}}] [{{number2}}]`. However, you should NEVER do this with the \
same number - if you want to cite `number1` multiple times for a sentence, only do \
`[{{number1}}]` not `[{{number1}}] [{{number1}}]`

You should use bullet points in your answer for readability. Put citations where they apply \
rather than putting them all at the end, however the after the end of your answer, you should \
include numbered URLS that correspond to each number citation in your answer.

If there is nothing in the context relevant to the question at hand, just say "Hmm, \
I'm not sure." Don't try to make up an answer.

Anything between the following `context` html blocks is retrieved from a knowledge \
bank, not part of the conversation with the user.

<context>
    {context}
<context/>

REMEMBER: If there is no relevant information within the context, just say "Hmm, I'm \
not sure." Don't try to make up an answer. Anything between the preceding 'context' \
html blocks is retrieved from a knowledge bank, not part of the conversation with the \
user. The current date is {current_date}.
"""

REPHRASE_TEMPLATE = """
Given the following conversation and a follow up question, rephrase the follow up question to be a standalone question.
Chat History: {chat_history}
Follow Up Input: {question}
Standalone Question:
"""

client = Client()
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"]



class ChatRequest(BaseModel):
    pass
    question: str
    chat_history: List[Tuple[str, str]] = Field(
        ..., extra={"widget": {"type": "chat", "input": "question", "output": "answer"}}
    )
   
    question: str

from langchain_community.retrievers.google_search import GoogleSearchAPIWrapper

class GoogleCustomSearchRetriever(BaseRetriever):
    search: Optional[GoogleSearchAPIWrapper] = None
    num_search_results: int = 6

    def clean_search_query(self, query: str) -> str:
        if query[0].isdigit():
            first_quote_pos = query.find('"')
            if first_quote_pos != -1:
                query = query[first_quote_pos + 1 :]
            if query.endswith('"'):
                query = query[:-1]
        return query.strip()

    def search_tool(self, query: str, num_search_results: int = 1) -> List[dict]:
        query_clean = self.clean_search_query(query)
        result = self.search.results(query_clean, num_search_results)
        return result

    def _get_relevant_documents(
        self, query: str, *, run_manager: CallbackManagerForRetrieverRun
    ):
        if os.environ.get("GOOGLE_API_KEY", None) is None:
            self.search = GoogleSearchAPIWrapper()  # Replace with the appropriate initialization of GoogleSearchAPIWrappervided")
        if self.search is None:
            self.search = GoogleSearchAPIWrapper()
        urls_to_look = []
        search_results = self.search_tool(query, self.num_search_results)
        for res in search_results:
            if res.get("link", None):
                urls_to_look.append(res["link"])
        loader = AsyncHtmlLoader(urls_to_look)
        html2text = Html2TextTransformer()
        docs = loader.load()
        docs = list(html2text.transform_documents(docs))
        for i in range(len(docs)):
            if search_results[i].get("title", None):
                docs[i].metadata["title"] = search_results[i]["title"]
        return docs


def get_retriever():
    embeddings = OpenAIEmbeddings()
    splitter = RecursiveCharacterTextSplitter(chunk_size=800, chunk_overlap=20)
    relevance_filter = EmbeddingsFilter(embeddings=embeddings, similarity_threshold=0.8)
    pipeline_compressor = DocumentCompressorPipeline(
        transformers=[splitter, relevance_filter]
    )
    base_tavily_retriever = TavilySearchAPIRetriever(
        k=6, include_raw_content=True, include_images=False
    )
    # Use the base retriever directly if ContextualCompressionRetriever is not available
    tavily_retriever = base_tavily_retriever
    base_google_retriever = GoogleCustomSearchRetriever()
    google_retriever = base_google_retriever
    base_you_retriever = YouRetriever(
        ydc_api_key=os.environ.get("YDC_API_KEY", "not_provided")
    )
    you_retriever = base_you_retriever
    base_kay_retriever = KayAiRetriever.create(
        dataset_id="company", data_types=["10-K", "10-Q"], num_contexts=6
    )
    kay_retriever = base_kay_retriever
    base_kay_press_release_retriever = KayAiRetriever.create(
        dataset_id="company", data_types=["PressRelease"], num_contexts=6
    )
    kay_press_release_retriever = ContextualCompressionRetriever(
        base_compressor=pipeline_compressor,
        base_retriever=base_kay_press_release_retriever,
    )
    return tavily_retriever.configurable_alternatives(
        ConfigurableField(id="retriever"),
        default_key="tavily",
        google=google_retriever,
        you=you_retriever,
        kay=kay_retriever,
        kay_press_release=kay_press_release_retriever,
    ).with_config(run_name="FinalSourceRetriever")

def create_retriever_chain(
    llm: BaseLanguageModel, retriever: BaseRetriever
) -> Runnable:
    CONDENSE_QUESTION_PROMPT = PromptTemplate.from_template(REPHRASE_TEMPLATE)
    condense_question_chain = (
        CONDENSE_QUESTION_PROMPT | llm | StrOutputParser()
    ).with_config(run_name="CondenseQuestion")
    conversation_chain = condense_question_chain | retriever
    return RunnableBranch(
        RunnableLambda(lambda x: bool(x.get("chat_history"))).with_config(
            run_name="HasChatHistoryCheck"
        ),
        conversation_chain.with_config(run_name="RetrievalChainWithHistory"),
        RunnableLambda(itemgetter("question")).with_config(
            run_name="Itemgetter:question"
        )
        | retriever
        .with_config(run_name="RetrievalChainWithNoHistory"),
    ).with_config(run_name="RouteDependingOnChatHistory")

def serialize_history(request: ChatRequest):
    chat_history = request.get("chat_history", [])
    converted_chat_history = []
    for message in chat_history:
        if message[0] == "human":
            converted_chat_history.append(HumanMessage(content=message[1]))
        elif message[0] == "ai":
            converted_chat_history.append(AIMessage(content=message[1]))
    return converted_chat_history

    formatted_docs = []
    # Add indented block of code here Remove the unused variable 'i'ument]) -> str:
    formatted_docs = []
    for i, doc in enumerate(docs):
        doc_string = f"{doc.page_content}"
        formatted_docs.append(doc_string)
    return "\n".join(formatted_docs)

def create_chain(
    retriever_chain = create_retriever_chain(llm, retriever) | RunnableLambda()
) -> Runnable:
    retriever_chain = create_retriever_chain(llm, retriever) | RunnableLambda()
    _context = RunnableMap(
        context=retriever_chain.with_config(run_name="RetrievalChain"),
        question=RunnableLambda(itemgetter("question")).with_config(
            run_name="Itemgetter:question"
        ),
        chat_history=RunnableLambda(itemgetter("chat_history")).with_config(
            run_name="Itemgetter:chat_history"
        ),
    ),
    run_name="Itemgetter:chat_history"
)
    prompt = ChatPromptTemplate.from_messages(
        ("system", RESPONSE_TEMPLATE),
        MessagesPlaceholder(variable_name="chat_history"),
    response_synthesizer = (prompt | llm | StrOutputParser()).with_config()
    ).partial(current_date=datetime.now().isoformat())
    response_synthesizer = (prompt | llm | StrOutputParser()).with_config()
    RunnableMap(
        context=retriever_chain.with_config(run_name="RetrievalChain"),
        question=RunnableLambda(itemgetter("question")).with_config(
        chat_history=RunnableLambda(serialize_history).with_config(
            run_name="SerializeHistory"
        ),
        ),
        chat_history=RunnableLambda(itemgetter("chat_history")).with_config(
            run_name="Itemgetter:chat_history"
        ),
    )
            run_name="Itemgetter:question"
        ),
        chat_history=RunnableLambda(serialize_history).with_config(
            run_name="SerializeHistory"
        | _context | response_synthesizer)
    ) | _context | response_synthe| _context | response_synthesizer)zer   ),
        | _context | response_s   ),
        | _context | response_synthesizer)
    )

dir_path = os.path.dirname(os.path.realpath(__file__))
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = (
    dir_path + "/" + ".google_vertex_ai_credentials.json"
)
has_google_creds = os.path.isfile(os.environ["GOOGLE_APPLICATION_CREDENTIALS"])

llm = ChatOpenAI(
    model="gpt-4o",
    # model="gpt-4",
    streaming=True,
    temperature=0.1,
).configurable_alternatives(
    ConfigurableField(id="llm"),
    default_key="openai",
    anthropic=ChatAnthropic(
        model="claude-3-opus-20240229",
        max_tokens=16384,
        temperature=0.1,
        anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY", "not_provided"),
    ),
)

if has_google_creds:
    llm = ChatOpenAI(
        model="gpt-4o",
        # model="gpt-4",
        streaming=True,
        temperature=0.1,
    ).configurable_alternatives(
        ConfigurableField(id="llm"),
        default_key="openai",
        anthropic=ChatAnthropic(
            model="claude-3-opus-20240229",
            max_tokens=16384,
            temperature=0.1,
            anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY", "not_provided"),
        ),
        googlevertex=ChatVertexAI(
            model_name="chat-bison-32k",
            temperature=0.1,
            max_output_tokens=8192,
            stream=True,
        ),
    )

retriever = get_retriever()
chain = create_chain(llm, retriever)

@app.post("/chat/stream_log")
async def chat(request: ChatRequest):
    logger.info(f"Received chat request: {request}")
    try:
        logger.info("Invoking the chain with the request data...")
        result = await chain.ainvoke(request.dict())
        logger.info(f"Chain invocation successful. Result: {result}")
        return result
    except Exception as e:
        logger.exception(f"An error occurred while processing the chat request: {str(e)}")
        return {"error": "An internal server error occurred. Please try again later.", "code": 500}

class SendFeedbackBody(BaseModel):
    run_id: UUID
    key: str = "user_score"
    score: Union[float, int, bool, None] = None
    feedback_id: Optional[UUID] = None
    comment: Optional[str] = None

@app.post("/feedback")
async def send_feedback(body: SendFeedbackBody):
    try:
        logger.info(f"Received feedback: {body}")
        client.create_feedback(
            body.run_id,
            body.key,
            score=body.score,
            comment=body.comment,
            feedback_id=body.feedback_id,
        )
        logger.info("Feedback posted successfully")
        return {"result": "posted feedback successfully", "code": 200}
    except Exception as e:
        logger.exception(f"An error occurred while posting feedback: {str(e)}")
        return {"error": "An internal server error occurred. Please try again later.", "code": 500}

class UpdateFeedbackBody(BaseModel):
    feedback_id: UUID
    score: Union[float, int, bool, None] = None
    comment: Optional[str] = None

@app.patch("/feedback")
async def update_feedback(body: UpdateFeedbackBody):
    feedback_id = body.feedback_id
    if feedback_id is None:
        logger.warning("No feedback ID provided")
        return {
            "result": "No feedback ID provided",
            "code": 400,
        }
    try:
        logger.info(f"Updating feedback with ID: {feedback_id}")
        client.update_feedback(
            feedback_id,
            score=body.score,
            comment=body.comment,
        )
        logger.info("Feedback updated successfully")
        return {"result": "patched feedback successfully", "code": 200}
    except Exception as e:
        logger.exception(f"An error occurred while updating feedback: {str(e)}")
        return {"error": "An internal server error occurred. Please try again later.", "code": 500}

async def _arun(func, *args, **kwargs):
    return await asyncio.get_running_loop().run_in_executor(None, func, *args, **kwargs)

async def aget_trace_url(run_id: str) -> str:
    for i in range(5):
        try:
            await _arun(client.read_run, run_id)
        except Exception:  # Replace langsmith.utils.LangSmithError with the appropriate exception type
await asyncio.sleep(1**i)
    if await _arun(client.run_is_shared, run_id):
        return await _arun(client.read_run_shared_link, run_id)
    return await _arun(client.share_run, run_id)

class GetTraceBody(BaseModel):
    run_id: UUID

@app.post("/get_trace")
async def get_trace(body: GetTraceBody):
    run_id = body.run_id
    if run_id is None:
        logger.warning("No LangSmith run ID provided")
        return {
            "result": "No LangSmith run ID provided",
            "code": 400,
        }
    try:
        logger.info(f"Getting trace URL for run ID: {run_id}")
        trace_url = await aget_trace_url(str(run_id))
        logger.info(f"Trace URL retrieved: {trace_url}")
        return trace_url
    except Exception as e:
        logger.exception(f"An error occurred while getting the trace URL: {str(e)}")
        return {"error": "An internal server error occurred. Please try again later.", "code": 500}

import uvicorn

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8080)
