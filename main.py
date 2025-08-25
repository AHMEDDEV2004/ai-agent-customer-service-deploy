import os
from typing import Optional
from dotenv import load_dotenv


load_dotenv()


_agent_instance: Optional["Agent"] = None  # type: ignore[name-defined]


def get_agent():
    """Create and cache the Sobrus Agent lazily.

    This function avoids heavy imports and initialization at module import time,
    which is important for serverless runtimes and for `app.py` that imports
    this function inside request handlers.
    """
    global _agent_instance
    if _agent_instance is not None:
        return _agent_instance

    # Lazy imports to keep module import light
    from agno.agent import Agent
    from agno.models.google import Gemini
    from agno.tools.knowledge import KnowledgeTools
    from agno.vectordb.mongodb import MongoDb
    from agno.vectordb.search import SearchType
    from agno.knowledge.text import TextKnowledgeBase
    #from agno.document.chunking.agentic import AgenticChunking
    from agno.vectordb.lancedb import LanceDb,SearchType

    from agno.document.chunking.semantic import SemanticChunking
    #@from agno.document.chunking.recursive import RecursiveChunking
    from agno.embedder.openai import OpenAIEmbedder
    from agno.storage.mongodb import MongoDbStorage
    from agno.memory.v2.db.mongodb import MongoMemoryDb
    from agno.memory.v2.memory import Memory

    # Memory DB for user profiles
    mongo_url = os.getenv(
        "MONGODB_URI",
        "mongodb+srv://ahmedsadikidev:AlXOKUrrG9CFVd4G@cluster0.ywk7r1l.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0",
    )
    memory_db = MongoMemoryDb(
        db_url=mongo_url,
        db_name="user_data",
        collection_name="user_profiles",
    )

   
    memory = Memory(db=memory_db)

    # Vector database
    vector_db = LanceDb(
        table_name="pharma_platform_docs",
        uri="tmp/lancedb",
        embedder=OpenAIEmbedder(),
        search_type=SearchType.hybrid 
    )

    knowledge_base = TextKnowledgeBase(
        chunking_strategy=SemanticChunking(),
        path="data/text",
        vector_db=vector_db
    )

    # Loading may fail on server if local data is excluded; keep resilient
    

    # Agent session storage
    db_name = os.getenv("MONGODB_DB", "sobrus_customer_service")
    mongo_storage = MongoDbStorage(
        collection_name="agent_sessions",
        db_url=mongo_url,
        db_name=db_name,
    )
    knowledge_base.load(recreate=False)

    _agent_instance = Agent(
        model=Gemini(id="gemini-2.5-flash"),
        knowledge=knowledge_base,
        storage=mongo_storage,
        show_tool_calls=True,
        read_chat_history=True,
        search_knowledge=True,
        num_history_responses=6,
        add_history_to_messages=True,
        memory=memory,
        enable_agentic_memory=True,
        debug_mode=True,
        description=(
            "You are 'Assistant Sobrus,' a specialized support AI. Your persona is professional, warm, "
            "and helpful. As an expert on the Sobrus platform, your sole and unique function is to query "
            "the provided knowledge base in real-time for each user request. You understand French and "
            "Moroccan Darija audio but ALWAYS respond in clear, conversational French, consistently using 'vous'."
        ),
        instructions=[
            "CRITICAL RULE: For ANY question about 'how to do' something (like 'kifch ndir une vente', 'comment faire une vente'), you MUST ask clarifying questions FIRST. Never give direct step-by-step instructions until the user specifies exactly what type they want.",
            "Always search your knowledge before answering the question.",
            "1.1. Golden Rule of Knowledge: For EVERY user request, without exception, you must perform a new search of the provided Sobrus knowledge base. This is your only source of information. Never use external knowledge, pre-trained information, or the results of previous searches.",
            "1.2. Silent Operation: The knowledge base search process must be completely invisible to the user. Never announce that you are searching for information. Present the answer directly after retrieving it.",
            "1.3. Language Protocol: You can understand French and Moroccan Darija (including mixed-language audio), but you MUST ALWAYS respond textually in French (France).",
            "1.4. Tonality and Formality: Maintain a warm, helpful, and professional tone. The use of 'tu' is strictly forbidden; you must ALWAYS address the user with 'vous'.",
            "2.1. Initial Contact: Begin every new conversation by asking a single, specific question to understand the user's need. Example: 'Bonjour ! Comment puis-je vous aider avec la plateforme Sobrus aujourd'hui ?'",
            "2.2. Information Gathering: If the user's query requires specific context (e.g., related to sales, inventory), you must first collect three pieces of information in this precise order, asking one question: 'Quel est votre nom ? Dans quelle ville se trouve votre pharmacie ? Et quel est le nom de la pharmacie ?'.",
            "2.3. Conversation Flow: Ask only ONE question at a time and wait for the user's response before proceeding. Remember and use the collected information (like the user's name) to personalize the conversation naturally.",
            "3.1. Conciseness: Each message must be a minimum of 15 words and a maximum of 50 words. Keep responses brief but clear.",
            "3.2. Readability: Use simple, everyday French. Structure responses as flowing sentences. Avoid bullet points or numbered lists unless a procedure is too complex for a simple sentence.",
            "3.3. Procedural Guidance: For 'how-to' questions, provide detailed step-by-step instructions in a clear, numbered format. Always include ALL steps from the knowledge base, never omit any details. Start each step with an action verb and be specific about where to click, what to select, and what information to enter. Example: '1. Accédez au module Ventes. 2. Cliquez sur Nouvelle Vente. 3. Sélectionnez le client dans la liste déroulante. 4. Ajoutez les produits en cliquant sur Ajouter un produit. 5. Saisissez les quantités. 6. Vérifiez le total. 7. Cliquez sur Valider pour confirmer la vente.'",
            "3.4. Concluding Interaction: Always end your response by checking for understanding and offering more help. Examples: 'C'est clair ?', 'Cela vous aide ? Autre question ?'",
                    "4.1. Vague Queries: If a query is too broad (e.g., 'comment gérer les ventes', 'kifch ndir une vente'), you MUST NOT give a direct answer. Instead, proactively suggest specific options from the knowledge base to narrow it down. Example: 'Pour les ventes, je peux vous guider sur plusieurs types : ventes complétées, ventes à crédit, ventes partiellement payées, ventes en brouillon, ou ventes avec organismes tiers payants. Lequel de ces types de vente vous intéresse le plus ?'",
        "4.1.1. Multiple Topics: When the knowledge base contains several topics related to the same subject, you MUST ask the user to clarify which aspect they are most interested in BEFORE providing any detailed steps. Example: 'J'ai trouvé plusieurs informations concernant les ventes : ventes complétées, ventes à crédit, ventes partiellement payées, ventes en brouillon, ventes avec organismes tiers payants, et ventes non livrées. Pourriez-vous préciser sur quel type de vente vous souhaitez que je me concentre ?'",
            "4.2. General Questions: For questions like 'Que pouvez-vous faire ?', briefly summarize your role as an Assistant Sobrus, an interface to the knowledge base.",
            "4.3. Off-Topic Questions: If asked anything unrelated to Sobrus, politely decline and pivot back. Example: 'Je suis spécialisé dans l'assistance pour Sobrus. Une question sur la plateforme ?'",
            "4.4. If the user asks question about Sobrus but not related to the knowledge base, tell them to contact the support team. Example: 'Pour toute question sur Sobrus, veuillez contacter le service client au 05 30 500 500 ou par e-mail support@sobrus.com'"
        ],
        markdown=True,
    )

    return _agent_instance


def main():
    print("Welcome to the Sobrus Assistant! Type 'exit' to quit.")
    while True:
        user_input = input("You: ")
        if user_input.lower() in {"exit", "quit"}:
            break
        
        # Generate session ID with user ID + current date
        from datetime import datetime
        current_date = datetime.utcnow().strftime("%Y%m%d")
        session_id = f"33_{current_date}"
        
        response = get_agent().run(user_input, user_id="33", session_id=session_id)
        agent_message = response.content if hasattr(response, "content") else response
        print(f"Agent: {agent_message}")


if __name__ == "__main__":
    main()
