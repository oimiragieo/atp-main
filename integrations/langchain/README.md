# ATP LangChain Integration

This package provides comprehensive LangChain integration for the ATP (AI Text Processing) platform, enabling seamless use of ATP's enterprise AI capabilities within LangChain workflows.

## Features

- **LLM Integration**: Full LangChain LLM interface with ATP backend
- **Chat Model Support**: Native chat model integration with conversation handling
- **Memory Integration**: Persistent conversation memory using ATP's memory gateway
- **Embeddings Support**: Text embeddings through ATP's embedding endpoints
- **Async Support**: Full async/await support for concurrent operations
- **Streaming**: Real-time streaming responses
- **Error Handling**: Robust retry mechanisms and error recovery
- **Enterprise Features**: Rate limiting, authentication, and monitoring

## Installation

```bash
# Install LangChain (required)
pip install langchain

# Install additional dependencies for examples
pip install faiss-cpu  # For vector store examples
```

## Quick Start

### Basic LLM Usage

```python
from integrations.langchain import ATPLangChainLLM

# Initialize ATP LLM
llm = ATPLangChainLLM(
    atp_base_url="http://localhost:8000",
    atp_api_key="your-api-key",
    model="gpt-4",
    temperature=0.7
)

# Use with LangChain
response = llm("What are the benefits of microservices architecture?")
print(response)
```

### Chat Model Usage

```python
from integrations.langchain import ATPChatModel
from langchain.schema import HumanMessage, SystemMessage

# Initialize ATP Chat Model
chat_model = ATPChatModel(
    atp_base_url="http://localhost:8000",
    atp_api_key="your-api-key",
    model="gpt-4"
)

# Create conversation
messages = [
    SystemMessage(content="You are a helpful AI assistant."),
    HumanMessage(content="Explain quantum computing in simple terms.")
]

response = chat_model(messages)
print(response.content)
```

### Memory Integration

```python
from integrations.langchain import ATPMemoryStore, ATPChatModel
from langchain.chains import ConversationChain

# Initialize components
chat_model = ATPChatModel(atp_base_url="http://localhost:8000")
memory = ATPMemoryStore(
    atp_memory_url="http://localhost:8001",
    session_id="user_123"
)

# Create conversation with memory
conversation = ConversationChain(
    llm=chat_model,
    memory=memory
)

# Have a conversation
response1 = conversation.predict(input="My name is Alice.")
response2 = conversation.predict(input="What's my name?")  # Will remember Alice
```

### Embeddings Usage

```python
from integrations.langchain import ATPEmbeddings
from langchain.vectorstores import FAISS
from langchain.docstore.document import Document

# Initialize embeddings
embeddings = ATPEmbeddings(
    atp_base_url="http://localhost:8000",
    model="text-embedding-ada-002"
)

# Create documents
docs = [
    Document(page_content="ATP is an enterprise AI platform."),
    Document(page_content="It provides routing and load balancing."),
    Document(page_content="ATP supports multiple AI providers.")
]

# Create vector store
vectorstore = FAISS.from_documents(docs, embeddings)

# Search for similar documents
results = vectorstore.similarity_search("What is ATP?", k=2)
```

## Advanced Usage

### Streaming Responses

```python
from integrations.langchain import ATPLangChainLLM

# Enable streaming
llm = ATPLangChainLLM(
    atp_base_url="http://localhost:8000",
    streaming=True
)

# Stream response
for chunk in llm.stream("Write a short story about AI."):
    print(chunk.text, end="", flush=True)
```

### Async Operations

```python
import asyncio
from integrations.langchain import ATPChatModel

async def async_example():
    chat_model = ATPChatModel(atp_base_url="http://localhost:8000")
    
    # Process multiple prompts concurrently
    prompts = ["Explain AI", "What is ML?", "Define NLP"]
    tasks = [chat_model.agenerate([prompt]) for prompt in prompts]
    results = await asyncio.gather(*tasks)
    
    for result in results:
        print(result.generations[0].message.content)

# Run async example
asyncio.run(async_example())
```

### Custom Chains

```python
from langchain.chains import LLMChain
from langchain.prompts import PromptTemplate
from integrations.langchain import ATPLangChainLLM

# Create custom prompt template
template = """
You are a code reviewer. Review this {language} code:

{code}

Provide feedback on:
1. Code quality
2. Potential issues
3. Improvements
"""

prompt = PromptTemplate(
    input_variables=["language", "code"],
    template=template
)

# Create chain
llm = ATPLangChainLLM(atp_base_url="http://localhost:8000")
chain = LLMChain(llm=llm, prompt=prompt)

# Use chain
result = chain.run(
    language="Python",
    code="def factorial(n): return 1 if n <= 1 else n * factorial(n-1)"
)
```

### Agent Integration

```python
from langchain.agents import initialize_agent, AgentType, Tool
from integrations.langchain import ATPLangChainLLM

def calculator(expression: str) -> str:
    """Calculate mathematical expressions."""
    try:
        return str(eval(expression))
    except:
        return "Invalid expression"

# Define tools
tools = [
    Tool(
        name="Calculator",
        func=calculator,
        description="Use for mathematical calculations"
    )
]

# Create agent
llm = ATPLangChainLLM(atp_base_url="http://localhost:8000")
agent = initialize_agent(
    tools=tools,
    llm=llm,
    agent=AgentType.ZERO_SHOT_REACT_DESCRIPTION
)

# Use agent
result = agent.run("What is 15 * 23 + 45?")
```

## Configuration

### Environment Variables

```bash
# ATP Configuration
export ATP_BASE_URL="http://localhost:8000"
export ATP_MEMORY_URL="http://localhost:8001"
export ATP_API_KEY="your-api-key"

# Model Configuration
export ATP_DEFAULT_MODEL="gpt-4"
export ATP_DEFAULT_TEMPERATURE="0.7"
```

### Configuration Options

| Parameter | Description | Default |
|-----------|-------------|---------|
| `atp_base_url` | ATP API base URL | `http://localhost:8000` |
| `atp_memory_url` | ATP Memory Gateway URL | `http://localhost:8001` |
| `atp_api_key` | API key for authentication | `None` |
| `model` | Model to use | `gpt-4` |
| `temperature` | Sampling temperature | `0.7` |
| `max_tokens` | Maximum tokens to generate | `None` |
| `streaming` | Enable streaming responses | `False` |
| `request_timeout` | Request timeout in seconds | `60` |
| `max_retries` | Maximum retry attempts | `3` |

## Error Handling

The integration includes robust error handling:

```python
from integrations.langchain import ATPLangChainLLM
import logging

# Enable logging
logging.basicConfig(level=logging.INFO)

# Configure with retries
llm = ATPLangChainLLM(
    atp_base_url="http://localhost:8000",
    max_retries=5,
    retry_delay=2.0,
    request_timeout=120
)

try:
    response = llm("Your prompt here")
except Exception as e:
    print(f"Error: {e}")
```

## Examples

Run the comprehensive examples:

```python
from integrations.langchain.examples import ATPLangChainExamples

# Initialize examples
examples = ATPLangChainExamples(
    atp_base_url="http://localhost:8000",
    atp_memory_url="http://localhost:8001"
)

# Run all examples
examples.run_all_examples()
```

## Integration with LangChain Ecosystem

### Vector Stores

```python
from langchain.vectorstores import Chroma, Pinecone, Weaviate
from integrations.langchain import ATPEmbeddings

embeddings = ATPEmbeddings(atp_base_url="http://localhost:8000")

# Use with any LangChain vector store
vectorstore = Chroma.from_texts(
    texts=["Document 1", "Document 2"],
    embedding=embeddings
)
```

### Document Loaders

```python
from langchain.document_loaders import TextLoader, PDFLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from integrations.langchain import ATPLangChainLLM

# Load and process documents
loader = TextLoader("document.txt")
documents = loader.load()

# Split documents
text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000)
docs = text_splitter.split_documents(documents)

# Process with ATP
llm = ATPLangChainLLM(atp_base_url="http://localhost:8000")
# ... use with chains
```

### Callbacks and Monitoring

```python
from langchain.callbacks import StdOutCallbackHandler
from integrations.langchain import ATPChatModel

# Use with callbacks
chat_model = ATPChatModel(atp_base_url="http://localhost:8000")

response = chat_model(
    messages=[HumanMessage(content="Hello")],
    callbacks=[StdOutCallbackHandler()]
)
```

## Performance Optimization

### Batch Processing

```python
from integrations.langchain import ATPEmbeddings

embeddings = ATPEmbeddings(
    atp_base_url="http://localhost:8000",
    batch_size=50  # Process 50 texts at once
)

# Efficiently process large document sets
large_text_list = ["text1", "text2", ...]  # 1000+ texts
embeddings_result = embeddings.embed_documents(large_text_list)
```

### Connection Pooling

The integration automatically handles connection pooling and session management for optimal performance.

## Security

- API keys are automatically hidden in LangChain tracing
- HTTPS support for secure communication
- Request/response validation
- Rate limiting integration

## Troubleshooting

### Common Issues

1. **Connection Errors**: Verify ATP services are running and accessible
2. **Authentication Errors**: Check API key configuration
3. **Rate Limiting**: Implement exponential backoff (built-in)
4. **Memory Issues**: Use appropriate batch sizes for large datasets

### Debug Mode

```python
import logging
logging.basicConfig(level=logging.DEBUG)

# This will show detailed request/response information
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality
4. Submit a pull request

## License

Licensed under the Apache License, Version 2.0. See LICENSE file for details.