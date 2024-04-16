# Google Cloud Run LangChain API


This repository contains the code for a Google Cloud Run service that provides an API for interacting with LangChain, a framework for building applications with large language models.

**Overview**

The API is built using FastAPI and allows users to send chat requests to the service. The service uses various LangChain components such as retrievers, document loaders, and chat models to generate responses based on the provided context and user input.

****API Endpoints**

**POST /chat/stream_log****
This endpoint accepts a ChatRequest object containing the user's question and chat history. It invokes the LangChain chain with the request data and returns the generated response.
Example request body:
{
  "question": "What is LangChain?",
  "chat_history": [
    ["human", "Hello!"],
    ["ai", "Hi there! How can I assist you today?"]
  ]
}

**Configuration**

The service requires the following environment variables to be set:
**TAVILY_API_KEY**: API key for the Tavily search service

**OPENAI_API_KEY**: API key for OpenAI's language models

**LANGCHAIN_API_KEY**: API key for LangChain

**KAY_API_KEY**: API key for the Kay AI service

The Service URL is https://googlecloudlangchain-rackdzwlha-uc.a.run.app 

## License

This library is licensed under Apache 2.0. Full license text is available in [LICENSE](LICENSE).
