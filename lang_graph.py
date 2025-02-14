import os
from dotenv import load_dotenv

load_dotenv()

os.environ["GROQ_API_KEY"] = os.getenv("GROQ_API_KEY")
os.environ["TAVILY_API_KEY"] = os.getenv("TAVILY_API_KEY")

os.environ["LANGCHAIN_TRACING_V2"] = "true"
os.environ["LANGCHAIN_PROJECT"] = "multi-agent-search_test"
os.environ["LANGCHAIN_API_KEY"] = os.getenv("LANGCHAIN_API_KEY")


#Import Library for tools:

from typing import Annotated
from langchain_community.tools.tavily_search import TavilySearchResults
from langchain_core.tools import tool
from langchain_experimental.utilities import PythonREPL


#Import Library for Agent Supervisor:

from typing import Literal
from typing_extensions import TypedDict

from langchain_groq import ChatGroq
from langgraph.graph import MessagesState
from langgraph.types import Command
from langchain_core.messages import  trim_messages
from langgraph.checkpoint.memory import MemorySaver
from langchain_core.messages import HumanMessage
from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import create_react_agent
from langgraph.graph.message import add_messages



def get_graph(user_input):
    

    #Create tools:

    tavily_tool = TavilySearchResults(max_results=5)
    
    repl = PythonREPL()


    @tool
    def python_rep_tool(code: Annotated[str, "Python code to execute to generate your chart."]) :
        """Use this to execute python code and do math. If you want to see the output of a value,
        you should print it out with `print(...)`. This is visible to the user."""
        try:
            result = repl.run(code)
        except BaseException as e:
            return f"Failed to execute. Error: {repr(e)}"
        result_str = f"Successfully executed:\n '''python\n{code}\n'''\nStdout: {result}"
        return result_str
    


    #Create Agent Supervisor: 

    members = ["researcher", "coder"]

    system_prompt =(
        f"You are a supervisor tasked with managing a conversation between the following workers: {members}. Your role is to route the user's request to the appropriate workers based on the task at hand. "
        "Here are the rules you must follow:"
        f"1. **Routing to Workers**: When a user request requires a specific worker, respond with the name of the worker {members} to route the request to that worker."
        "2. **Handling Results**: After receiving results from a worker, evaluate whether the user's request has been fully addressed. If the request is complete, respond with the keyword FINISH to indicate the end of the workflow."
        "3. **Final Response**: When you decide to end the workflow, ensure your response is with their results ."
        " Ensure all tool calls are formatted correctly."
        )
    

    class Router(TypedDict):
        """Worker to route to next. If no workers needed, route to FINISH."""
        next: Literal["researcher", "coder","FINISH"]

    
    llm = ChatGroq(groq_api_key=os.environ["GROQ_API_KEY"],model="mixtral-8x7b-32768",temperature=0, max_tokens=200)


    class State(MessagesState):
        next: str

    

    #Supervisor Agent:
    def supervisor_node(state: State) -> Command[Literal["researcher", "coder", "__end__"]]:
        messages = [
            {"role": "system", "content": system_prompt},
            ] + state["messages"]
        
        response = llm.with_structured_output(Router).invoke(messages)
        
        print('llm-response:',response)

        goto = response["next"]
        print("goto:",goto)

        if goto == "FINISH":
            goto = END
        return Command(goto=goto,update={"next": goto})
    

    
    #Search_Tool
    research_agent = create_react_agent(
        llm , tools=[tavily_tool], state_modifier="You are a researcher. DO NOT do any math operations.")
    

    def research_node(state: MessagesState) -> Command[Literal["supervisor"]]:
        result = research_agent.invoke(state)
        return Command(
            update={
                "messages": [
                    HumanMessage(content=result["messages"][-1].content, name="researcher")
            ]
            },
            goto="supervisor",
        )
    


    # Math_operator_Tool
    code_agent = create_react_agent(llm, tools=[python_rep_tool], state_modifier="You are a Math Operator Tool.do the math operations only.")


    def code_node(state: MessagesState) -> Command[Literal["supervisor"]]:
        result = code_agent.invoke(state)
        return Command(
            update={
                "messages": [
                    HumanMessage(content=result["messages"][-1].content, name="coder")
                ]
            },
            goto="supervisor",
        )
    
    
    #Construct Graph_Workflow

    builder = StateGraph(State)
    builder.add_edge(START, "supervisor")
    builder.add_node("supervisor", supervisor_node)
    builder.add_node("researcher", research_node)
    builder.add_node("coder", code_node)
    graph = builder.compile()




    #Invoke the Graph

    def call_agent(input):
        output = []
        for s in graph.stream({"messages": [("user", input)]}, subgraphs=True):
            print(s)
            print("----")
            output.append(s)

        a = output [-2][1]
        #print(a)

        if 'researcher' in a:
            output1 = a['researcher']['messages'][-1].content

        elif 'coder'in a:
            output1 = a['coder']['messages'][-1].content

        return output1
    
    
    d = call_agent(user_input)

    print("------------------------------------------------------------")
    print("\n")
    print("\n")
    print("\n")
    print("-----------------------------------------------------------")
    print(d)

    return d





