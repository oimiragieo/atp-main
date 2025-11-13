# Copyright 2025 ATP Project Contributors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""
ATP LangChain Integration Examples
This module provides examples of using ATP with LangChain.
"""

import asyncio
import os

try:
    from langchain.agents import AgentType, Tool, initialize_agent
    from langchain.chains import ConversationChain, LLMChain
    from langchain.chains.question_answering import load_qa_chain
    from langchain.chains.summarize import load_summarize_chain
    from langchain.document_loaders import TextLoader
    from langchain.prompts import ChatPromptTemplate, PromptTemplate
    from langchain.schema import AIMessage, HumanMessage, SystemMessage
    from langchain.text_splitter import RecursiveCharacterTextSplitter
    from langchain.vectorstores import FAISS
except ImportError:
    raise ImportError(
        "LangChain is required for ATP LangChain integration examples. Install it with: pip install langchain"
    )

from .atp_chat_model import ATPChatModel
from .atp_embeddings import ATPEmbeddings
from .atp_llm import ATPLangChainLLM
from .memory_integration import ATPMemoryStore


class ATPLangChainExamples:
    """Examples of ATP LangChain integration."""

    def __init__(
        self,
        atp_base_url: str = "http://localhost:8000",
        atp_memory_url: str = "http://localhost:8001",
        api_key: str = None,
    ):
        self.atp_base_url = atp_base_url
        self.atp_memory_url = atp_memory_url
        self.api_key = api_key or os.getenv("ATP_API_KEY")

        # Initialize ATP components
        self.llm = ATPLangChainLLM(atp_base_url=atp_base_url, atp_api_key=self.api_key, model="gpt-4", temperature=0.7)

        self.chat_model = ATPChatModel(
            atp_base_url=atp_base_url, atp_api_key=self.api_key, model="gpt-4", temperature=0.7
        )

        self.embeddings = ATPEmbeddings(
            atp_base_url=atp_base_url, atp_api_key=self.api_key, model="text-embedding-ada-002"
        )

        self.memory = ATPMemoryStore(
            atp_memory_url=atp_memory_url, atp_api_key=self.api_key, session_id="example_session"
        )

    def basic_llm_example(self) -> str:
        """Basic LLM usage example."""
        print("=== Basic LLM Example ===")

        # Simple prompt
        prompt = "What are the benefits of using AI in software development?"
        response = self.llm(prompt)

        print(f"Prompt: {prompt}")
        print(f"Response: {response}")

        return response

    def chat_model_example(self) -> str:
        """Chat model usage example."""
        print("\n=== Chat Model Example ===")

        messages = [
            SystemMessage(content="You are a helpful AI assistant specialized in software architecture."),
            HumanMessage(content="How would you design a microservices architecture for an e-commerce platform?"),
        ]

        response = self.chat_model(messages)

        print(f"Messages: {[msg.content[:50] + '...' for msg in messages]}")
        print(f"Response: {response.content}")

        return response.content

    def conversation_with_memory_example(self) -> str:
        """Conversation with memory example."""
        print("\n=== Conversation with Memory Example ===")

        # Create conversation chain with memory
        conversation = ConversationChain(llm=self.chat_model, memory=self.memory, verbose=True)

        # First interaction
        response1 = conversation.predict(input="My name is Alice and I'm a software engineer.")
        print(f"Response 1: {response1}")

        # Second interaction (should remember the name)
        response2 = conversation.predict(input="What's my name and profession?")
        print(f"Response 2: {response2}")

        return response2

    def prompt_template_example(self) -> str:
        """Prompt template example."""
        print("\n=== Prompt Template Example ===")

        # Create a prompt template
        template = """
        You are an expert code reviewer. Please review the following code and provide feedback:
        
        Code Language: {language}
        Code:
        {code}
        
        Please provide:
        1. Overall assessment
        2. Potential issues
        3. Suggestions for improvement
        """

        prompt = PromptTemplate(input_variables=["language", "code"], template=template)

        # Create chain
        chain = LLMChain(llm=self.llm, prompt=prompt)

        # Run the chain
        response = chain.run(
            language="Python",
            code="""
def fibonacci(n):
    if n <= 1:
        return n
    return fibonacci(n-1) + fibonacci(n-2)
            """,
        )

        print(f"Code Review Response: {response}")

        return response

    def document_qa_example(self) -> str:
        """Document Q&A with embeddings example."""
        print("\n=== Document Q&A Example ===")

        # Sample documents
        documents = [
            "ATP (AI Text Processing) is an enterprise platform for managing AI language models.",
            "The platform provides routing, load balancing, and failover capabilities.",
            "ATP supports multiple providers including OpenAI, Anthropic, and Google.",
            "The system includes comprehensive monitoring and analytics features.",
            "ATP offers enterprise-grade security with authentication and authorization.",
        ]

        # Create embeddings for documents
        self.embeddings.embed_documents(documents)

        # Create vector store
        # Note: In a real scenario, you'd use proper Document objects
        from langchain.docstore.document import Document

        docs = [Document(page_content=doc) for doc in documents]

        vectorstore = FAISS.from_documents(docs, self.embeddings)

        # Ask a question
        question = "What providers does ATP support?"
        relevant_docs = vectorstore.similarity_search(question, k=2)

        # Create Q&A chain
        qa_chain = load_qa_chain(self.llm, chain_type="stuff")

        # Get answer
        response = qa_chain.run(input_documents=relevant_docs, question=question)

        print(f"Question: {question}")
        print(f"Answer: {response}")

        return response

    def summarization_example(self) -> str:
        """Document summarization example."""
        print("\n=== Document Summarization Example ===")

        # Long text to summarize
        long_text = """
        Artificial Intelligence (AI) has revolutionized numerous industries and continues to shape the future of technology. 
        In software development, AI tools assist developers in writing code, debugging, and optimizing performance. 
        Machine learning algorithms can predict software bugs, suggest code improvements, and automate testing processes.
        
        Natural Language Processing (NLP) enables computers to understand and generate human language, leading to 
        applications like chatbots, translation services, and content generation. Computer vision allows machines 
        to interpret visual information, enabling applications in autonomous vehicles, medical imaging, and security systems.
        
        The integration of AI in business processes has led to increased efficiency, reduced costs, and improved 
        decision-making. However, it also raises concerns about job displacement, privacy, and ethical considerations 
        that need to be carefully addressed as AI technology continues to advance.
        """

        # Create document
        from langchain.docstore.document import Document

        doc = Document(page_content=long_text)

        # Create summarization chain
        summarize_chain = load_summarize_chain(self.llm, chain_type="stuff")

        # Generate summary
        summary = summarize_chain.run([doc])

        print(f"Original text length: {len(long_text)} characters")
        print(f"Summary: {summary}")

        return summary

    def streaming_example(self):
        """Streaming response example."""
        print("\n=== Streaming Example ===")

        # Enable streaming
        streaming_llm = ATPLangChainLLM(
            atp_base_url=self.atp_base_url, atp_api_key=self.api_key, streaming=True, temperature=0.8
        )

        prompt = "Write a short story about a robot learning to paint."

        print(f"Prompt: {prompt}")
        print("Streaming response:")

        # Stream the response
        for chunk in streaming_llm.stream(prompt):
            print(chunk.text, end="", flush=True)

        print("\n")

    async def async_example(self):
        """Async usage example."""
        print("\n=== Async Example ===")

        prompts = [
            "What is machine learning?",
            "Explain neural networks.",
            "What is deep learning?",
            "How does reinforcement learning work?",
        ]

        print("Processing multiple prompts concurrently...")

        # Process prompts concurrently
        tasks = [self.llm.agenerate([prompt]) for prompt in prompts]
        results = await asyncio.gather(*tasks)

        for i, result in enumerate(results):
            print(f"Prompt {i + 1}: {prompts[i]}")
            print(f"Response {i + 1}: {result.generations[0][0].text[:100]}...")
            print()

    def agent_example(self) -> str:
        """Agent with tools example."""
        print("\n=== Agent Example ===")

        # Define tools
        def calculator(expression: str) -> str:
            """Calculate mathematical expressions."""
            import ast
            import operator

            # Safe math operators only
            SAFE_OPERATORS = {
                ast.Add: operator.add,
                ast.Sub: operator.sub,
                ast.Mult: operator.mul,
                ast.Div: operator.truediv,
                ast.Pow: operator.pow,
                ast.USub: operator.neg,
            }

            def safe_eval_node(node):
                if isinstance(node, ast.Num):
                    return node.n
                elif isinstance(node, ast.BinOp):
                    op = SAFE_OPERATORS.get(type(node.op))
                    if op is None:
                        raise ValueError(f"Unsafe operation: {type(node.op).__name__}")
                    return op(safe_eval_node(node.left), safe_eval_node(node.right))
                elif isinstance(node, ast.UnaryOp):
                    op = SAFE_OPERATORS.get(type(node.op))
                    if op is None:
                        raise ValueError(f"Unsafe operation: {type(node.op).__name__}")
                    return op(safe_eval_node(node.operand))
                else:
                    raise ValueError(f"Unsafe node type: {type(node).__name__}")

            try:
                node = ast.parse(expression, mode='eval')
                result = safe_eval_node(node.body)
                return f"The result is: {result}"
            except Exception as e:
                return f"Error calculating: {e}"

        def text_length(text: str) -> str:
            """Count characters in text."""
            return f"The text has {len(text)} characters."

        tools = [
            Tool(
                name="Calculator",
                func=calculator,
                description="Use this to perform mathematical calculations. Input should be a valid mathematical expression.",
            ),
            Tool(
                name="TextLength",
                func=text_length,
                description="Use this to count characters in text. Input should be the text to count.",
            ),
        ]

        # Create agent
        agent = initialize_agent(tools=tools, llm=self.llm, agent=AgentType.ZERO_SHOT_REACT_DESCRIPTION, verbose=True)

        # Run agent
        response = agent.run("What is 15 * 23, and how many characters are in the word 'artificial intelligence'?")

        print(f"Agent response: {response}")

        return response

    def run_all_examples(self):
        """Run all examples."""
        print("Running ATP LangChain Integration Examples")
        print("=" * 50)

        try:
            # Sync examples
            self.basic_llm_example()
            self.chat_model_example()
            self.conversation_with_memory_example()
            self.prompt_template_example()
            self.document_qa_example()
            self.summarization_example()
            self.streaming_example()
            self.agent_example()

            # Async example
            print("\nRunning async example...")
            asyncio.run(self.async_example())

            print("\n" + "=" * 50)
            print("All examples completed successfully!")

        except Exception as e:
            print(f"Error running examples: {e}")
            raise


def main():
    """Main function to run examples."""
    # Initialize examples
    examples = ATPLangChainExamples(atp_base_url="http://localhost:8000", atp_memory_url="http://localhost:8001")

    # Run all examples
    examples.run_all_examples()


if __name__ == "__main__":
    main()
