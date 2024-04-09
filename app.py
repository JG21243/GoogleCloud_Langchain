
from utils.logging import logger
import signal
import sys
from types import FrameType

from flask import Flask, request, jsonify, render_template
from langchain_openai import ChatOpenAI
from langchain.memory import ChatMessageHistory
from langchain.agents import Tool, AgentExecutor, create_openai_tools_agent
from langchain_community.tools.tavily_search import TavilySearchResults
from langchain_core.messages import AIMessage, HumanMessage
from langchain import hub
from langchain_core.runnables.history import RunnableWithMessageHistory

app = Flask(__name__, static_folder='./templates', static_url_path='')

# Create a Tavily Search tool
tavily_search_tool = Tool(
    name="tavily-search",
    description="Tool for searching the web with Tavily",
    func=TavilySearchResults(max_results=5).invoke,
)

# Create an instance of the ChatOpenAI class
llm = ChatOpenAI()

# Add the Tavily Search tool to the list of tools
tools = [tavily_search_tool]

instructions = "You are a helpful assistant."
base_prompt = hub.pull("langchain-ai/openai-functions-template")
prompt = base_prompt.partial(instructions=instructions)

# Construct the OpenAI Tools agent
agent = create_openai_tools_agent(llm, tools, prompt)

# Create a chat message history
chat_history = ChatMessageHistory()

# Create an AgentExecutor instance to handle the chat history and tools
agent_executor = AgentExecutor(agent=agent, tools=tools, verbose=True)

# Using with chat history
agent_executor.invoke(
    {
        "input": "what's my name? Don't use tools to look this up unless you NEED to",
        "agent_scratchpad": "Your previous message",
        "chat_history": [
            HumanMessage(content="Your previous message"),
            AIMessage(content="Any intermediate steps"),
            AIMessage(content="Any agent scratchpad data"),
            # Add more chat history here if available
        ]
    }
)

@app.route('/')
def home():
    return app.send_static_file('index.html')

@app.route('/api/chat', methods=['POST'])
def chat_api():
    try:
        data = request.json
        if data is None:
            print("No valid JSON received")  # Debugging print
            return jsonify({'error': 'No valid JSON received'}), 400

        print("Received data:", data)  # Debugging print
        data["input"] = data.pop("message")
        bot_response = agent_executor.invoke(data)
        print("Bot response:", bot_response)  # Debugging print

        # Additional debugging prints:
        print("Type of bot response:", type(bot_response))
        print("Attributes of bot response:", dir(bot_response))

        return jsonify({'response': bot_response})
    except Exception as e:
        print("Error processing chat request:", e)  # Error logging
        return jsonify({'error': 'Failed to process chat request'}), 500


@app.route('/newpage')
def new_page():
    return render_template('main_content.html')

    # Updated to use render_template for serving the modularized main_content.html
    return render_template('main_content.html')

if __name__ == '__main__':
    chat_with_history = RunnableWithMessageHistory(
        agent_executor,
        lambda session_id: chat_history,
        input_messages_key="message",
        history_messages_key="chat_history",
    )
    app.run(debug=True, port=8080)

def shutdown_handler(signal_int: int, frame: FrameType) -> None:
    logger.info(f"Caught Signal {signal.strsignal(signal_int)}")

    from utils.logging import flush

    flush()

    # Safely exit program
    sys.exit(0)


if __name__ == "__main__":
    # Running application locally, outside of a Google Cloud Environment

    # handles Ctrl-C termination
    signal.signal(signal.SIGINT, shutdown_handler)

    app.run(host="localhost", port=8080, debug=True)
else:
    # handles Cloud Run container termination
    signal.signal(signal.SIGTERM, shutdown_handler)
