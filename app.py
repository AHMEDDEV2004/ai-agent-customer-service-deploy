import os
from datetime import datetime
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response as FastAPIResponse
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv


# ------------------------------------------------------------
# Environment & configuration
# ------------------------------------------------------------
load_dotenv()

MONGODB_URI = os.getenv(
    "MONGODB_URI"
)
DB_NAME = os.getenv("MONGODB_DB", "sobrus_customer_service")
COLLECTION_NAME = os.getenv("MONGODB_COLLECTION", "chat_messages")

# Twilio configuration
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_PHONE_NUMBER = os.getenv("TWILIO_PHONE_NUMBER")

# Note: Text-to-speech removed


# ------------------------------------------------------------
# External clients (lazy)
# ------------------------------------------------------------
def get_twilio_client():
    if not (TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN):
        return None
    from twilio.rest import Client  # lazy import
    return Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)


# ------------------------------------------------------------
# FastAPI app
# ------------------------------------------------------------
app = FastAPI()

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[ "*"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)


# ------------------------------------------------------------
# Database access
# Note: In Vercel's serverless runtime the event loop is created and closed
# per request. Creating a global Motor client can bind it to a closed loop
# on subsequent invocations. We therefore create and close the client within
# each DB operation to ensure it binds to the current loop.
# ------------------------------------------------------------


# ------------------------------------------------------------
# Utilities
# ------------------------------------------------------------
 
async def save_chat_message(user_id: str, message: str, sender: str, timestamp: datetime, 
                           audio_url: str = None, media_type: str = None, session_id: str = None) -> None:
    """Save a chat message to MongoDB with consistent structure."""
    document = {
        "user_id": user_id,
        "message": message,
        "sender": sender,
        "timestamp": timestamp,
        "session_id": session_id or f"{user_id}_session"
    }
    
    # Add media-related fields if present
    if audio_url:
        document["audio_url"] = audio_url
    if media_type:
        document["media_type"] = media_type
    
    await safe_db_insert(document)

async def get_chat_history(user_id: str, limit: int = 50, skip: int = 0) -> list:
    """Retrieve chat history for a specific user from MongoDB."""
    from motor.motor_asyncio import AsyncIOMotorClient  # lazy import to avoid event-loop binding
    client = AsyncIOMotorClient(MONGODB_URI)
    try:
        database = client[DB_NAME]
        collection = database[COLLECTION_NAME]
        
        # Query messages for the user, sorted by timestamp (newest first)
        cursor = collection.find(
            {"user_id": user_id}
        ).sort("timestamp", -1).skip(skip).limit(limit)
        
        messages = await cursor.to_list(length=limit)
        
        # Convert ObjectId to string for JSON serialization
        for message in messages:
            if "_id" in message:
                message["_id"] = str(message["_id"])
            if "timestamp" in message:
                message["timestamp"] = message["timestamp"].isoformat() + "Z"
        
        # Reverse to get chronological order (oldest first)
        messages.reverse()
        return messages
        
    except Exception as e:
        print(f"[get_chat_history] Error retrieving chat history: {e}")
        return []
    finally:
        client.close()

async def get_all_users_chat_history(limit: int = 20, skip: int = 0) -> list:
    """Retrieve chat history for all users from MongoDB."""
    from motor.motor_asyncio import AsyncIOMotorClient  # lazy import to avoid event-loop binding
    client = AsyncIOMotorClient(MONGODB_URI)
    try:
        database = client[DB_NAME]
        collection = database[COLLECTION_NAME]
        
        # Get all unique users first
        pipeline = [
            {"$group": {"_id": "$user_id"}},
            {"$sort": {"_id": 1}},
            {"$skip": skip},
            {"$limit": limit}
        ]
        
        users_cursor = collection.aggregate(pipeline)
        users = await users_cursor.to_list(length=limit)
        
        # For each user, get their latest message
        result = []
        for user in users:
            user_id = user["_id"]
            
            # Get the latest message for this user
            latest_message = await collection.find_one(
                {"user_id": user_id},
                sort=[("timestamp", -1)]
            )
            
            # Get message count for this user
            message_count = await collection.count_documents({"user_id": user_id})
            
            if latest_message:
                # Convert ObjectId to string for JSON serialization
                latest_message["_id"] = str(latest_message["_id"])
                if "timestamp" in latest_message:
                    latest_message["timestamp"] = latest_message["timestamp"].isoformat() + "Z"
                
                result.append({
                    "user_id": user_id,
                    "latest_message": latest_message,
                    "message_count": message_count,
                    "last_activity": latest_message["timestamp"]
                })
        
        return result
        
    except Exception as e:
        print(f"[get_all_users_chat_history] Error retrieving all users chat history: {e}")
        return []
    finally:
        client.close()

async def get_user_conversation_summary(user_id: str, limit: int = 10) -> dict:
    """Get a summary of a user's conversation including recent messages."""
    from motor.motor_asyncio import AsyncIOMotorClient  # lazy import to avoid event-loop binding
    client = AsyncIOMotorClient(MONGODB_URI)
    try:
        database = client[DB_NAME]
        collection = database[COLLECTION_NAME]
        
        # Get total message count
        total_messages = await collection.count_documents({"user_id": user_id})
        
        # Get recent messages
        cursor = collection.find(
            {"user_id": user_id}
        ).sort("timestamp", -1).limit(limit)
        
        recent_messages = await cursor.to_list(length=limit)
        
        # Convert ObjectId to string for JSON serialization
        for message in recent_messages:
            if "_id" in message:
                message["_id"] = str(message["_id"])
            if "timestamp" in message:
                message["timestamp"] = message["timestamp"].isoformat() + "Z"
        
        # Reverse to get chronological order
        recent_messages.reverse()
        
        # Get first and last activity
        first_message = await collection.find_one(
            {"user_id": user_id},
            sort=[("timestamp", 1)]
        )
        
        last_message = await collection.find_one(
            {"user_id": user_id},
            sort=[("timestamp", -1)]
        )
        
        summary = {
            "user_id": user_id,
            "total_messages": total_messages,
            "recent_messages": recent_messages,
            "first_activity": first_message["timestamp"].isoformat() + "Z" if first_message else None,
            "last_activity": last_message["timestamp"].isoformat() + "Z" if last_message else None
        }
        
        return summary
        
    except Exception as e:
        print(f"[get_user_conversation_summary] Error retrieving user summary: {e}")
        return {"user_id": user_id, "error": str(e)}
    finally:
        client.close()

async def db_insert(document: dict) -> None:
    from motor.motor_asyncio import AsyncIOMotorClient  # lazy import to avoid event-loop binding
    client = AsyncIOMotorClient(MONGODB_URI)
    try:
        database = client[DB_NAME]
        collection = database[COLLECTION_NAME]
        await collection.insert_one(document)
    finally:
        client.close()


async def safe_db_insert(document: dict) -> None:
    """Best-effort insert that never raises to the request handler."""
    try:
        # Skip if Mongo config is missing
        if not (MONGODB_URI and DB_NAME and COLLECTION_NAME):
            return
        await db_insert(document)
    except Exception as e:
        # Log and continue without failing the request
        print(f"[safe_db_insert] Skipping DB insert due to error: {e}")


def send_agent_response(user_id: str, agent_message: str):
    """Send agent response via Twilio or fallback to TwiML Response (text only)."""
    twilio_client = get_twilio_client()
    if twilio_client and TWILIO_PHONE_NUMBER:
        try:
            message = twilio_client.messages.create(
                from_=f"whatsapp:{TWILIO_PHONE_NUMBER}",
                body=agent_message.replace("**", "*"),
                to=f"whatsapp:{user_id}"
            )
            print(f"Text message sent via Twilio: {message.sid}")
            return FastAPIResponse(status_code=204)
        except Exception as e:
            print(f"Error sending message via Twilio: {e}")
            from twilio.twiml.messaging_response import MessagingResponse  # lazy import
            response = MessagingResponse()
            response.message(agent_message.replace("**", "*"))
            return FastAPIResponse(content=str(response), media_type="application/xml")
    else:
        from twilio.twiml.messaging_response import MessagingResponse  # lazy import
        response = MessagingResponse()
        response.message(agent_message.replace("**", "*"))
        return FastAPIResponse(content=str(response), media_type="application/xml")


def respond_twiml_text(message: str) -> FastAPIResponse:
    """Always return a valid TwiML response (for Twilio webhook) with given text."""
    try:
        from twilio.twiml.messaging_response import MessagingResponse  # lazy import
        resp = MessagingResponse()
        resp.message(message.replace("**", "*"))
        return FastAPIResponse(content=str(resp), media_type="application/xml")
    except Exception as exc:
        # As a last resort, return 200 with plain text
        print(f"[respond_twiml_text] Failed to build TwiML: {exc}")
        return FastAPIResponse(content=message, media_type="text/plain", status_code=200)


# ------------------------------------------------------------
# Routes
# ------------------------------------------------------------
@app.get("/api/chat/history/{user_id}")
async def get_chat_history_endpoint(
    user_id: str, 
    limit: int = 50, 
    skip: int = 0
):
    """
    Get chat history for a specific user.
    
    Args:
        user_id: The user ID to get history for
        limit: Maximum number of messages to return (default: 50, max: 100)
        skip: Number of messages to skip for pagination (default: 0)
    
    Returns:
        JSON response with chat history
    """
    # Validate parameters
    if not user_id:
        return JSONResponse(
            {"detail": "user_id is required"}, 
            status_code=400
        )
    
    if limit < 1 or limit > 100:
        return JSONResponse(
            {"detail": "limit must be between 1 and 100"}, 
            status_code=400
        )
    
    if skip < 0:
        return JSONResponse(
            {"detail": "skip must be non-negative"}, 
            status_code=400
        )
    
    try:
        # Check if MongoDB is configured
        if not (MONGODB_URI and DB_NAME and COLLECTION_NAME):
            return JSONResponse(
                {"detail": "Database not configured"}, 
                status_code=503
            )
        
        # Get chat history
        messages = await get_chat_history(user_id, limit, skip)
        
        return {
            "user_id": user_id,
            "messages": messages,
            "total_messages": len(messages),
            "limit": limit,
            "skip": skip
        }
        
    except Exception as e:
        import traceback
        print(f"[/api/chat/history/{user_id}] Error: {e}")
        print(traceback.format_exc())
        return JSONResponse(
            {"detail": "Internal server error"}, 
            status_code=500
        )

@app.get("/api/chat/users")
async def get_all_users_endpoint(
    limit: int = 20, 
    skip: int = 0,
    include_summary: bool = False
):
    """
    Get a list of all users with their chat history summary.
    
    Args:
        limit: Maximum number of users to return (default: 20, max: 100)
        skip: Number of users to skip for pagination (default: 0)
        include_summary: Whether to include detailed conversation summary (default: False)
    
    Returns:
        JSON response with list of users and their chat history
    """
    # Validate parameters
    if limit < 1 or limit > 100:
        return JSONResponse(
            {"detail": "limit must be between 1 and 100"}, 
            status_code=400
        )
    
    if skip < 0:
        return JSONResponse(
            {"detail": "skip must be non-negative"}, 
            status_code=400
        )
    
    try:
        # Check if MongoDB is configured
        if not (MONGODB_URI and DB_NAME and COLLECTION_NAME):
            return JSONResponse(
                {"detail": "Database not configured"}, 
                status_code=503
            )
        
        # Get all users with their chat history
        users_data = await get_all_users_chat_history(limit, skip)
        
        # If include_summary is True, add detailed conversation summary for each user
        if include_summary:
            for user_data in users_data:
                user_id = user_data["user_id"]
                summary = await get_user_conversation_summary(user_id, limit=10)
                user_data["conversation_summary"] = summary
        
        return {
            "users": users_data,
            "total_users": len(users_data),
            "limit": limit,
            "skip": skip,
            "include_summary": include_summary
        }
        
    except Exception as e:
        import traceback
        print(f"[/api/chat/users] Error: {e}")
        print(traceback.format_exc())
        return JSONResponse(
            {"detail": "Internal server error"}, 
            status_code=500
        )

@app.get("/api/chat/users/{user_id}/summary")
async def get_user_summary_endpoint(
    user_id: str,
    limit: int = 10
):
    """
    Get a detailed conversation summary for a specific user.
    
    Args:
        user_id: The user ID to get summary for
        limit: Maximum number of recent messages to include (default: 10, max: 50)
    
    Returns:
        JSON response with user conversation summary
    """
    # Validate parameters
    if not user_id:
        return JSONResponse(
            {"detail": "user_id is required"}, 
            status_code=400
        )
    
    if limit < 1 or limit > 50:
        return JSONResponse(
            {"detail": "limit must be between 1 and 50"}, 
            status_code=400
        )
    
    try:
        # Check if MongoDB is configured
        if not (MONGODB_URI and DB_NAME and COLLECTION_NAME):
            return JSONResponse(
                {"detail": "Database not configured"}, 
                status_code=503
            )
        
        # Get user conversation summary
        summary = await get_user_conversation_summary(user_id, limit)
        
        return summary
        
    except Exception as e:
        import traceback
        print(f"[/api/chat/users/{user_id}/summary] Error: {e}")
        print(traceback.format_exc())
        return JSONResponse(
            {"detail": "Internal server error"}, 
            status_code=500
        )

@app.post("/api/chat")
async def chat_api(request: Request):
    try:
        data = await request.json()
    except Exception as e:
        print(f"[/api/chat] Failed to parse JSON body: {e}")
        data = {}

    user_id = data.get("user_id")
    user_message = data.get("message")
    if not user_id or not user_message:
        return JSONResponse({"detail": "user_id and message are required"}, status_code=400)

    timestamp = datetime.utcnow()
    session_id = f"{user_id}_session"

    # Store user message
    await save_chat_message(
        user_id=user_id,
        message=user_message,
        sender="user",
        timestamp=timestamp,
        session_id=session_id
    )

    from main import get_agent  # lazy import and construction
    try:
        agent_response = get_agent().run(
            user_message,
            user_id=user_id,
            session_id=session_id
        )
        agent_message = getattr(agent_response, 'content', None) or str(agent_response)
    except Exception as e:
        import traceback
        print("[/api/chat] Agent error:\n" + traceback.format_exc())
        agent_message = (
            "Désolé, une erreur est survenue en traitant votre demande. "
            "Réessayez dans un instant."
        )

    # Store agent message
    await save_chat_message(
        user_id=user_id,
        message=agent_message,
        sender="agent",
        timestamp=datetime.utcnow(),
        session_id=session_id
    )

    return {
        "user_id": user_id,
        "message": user_message,
        "agent_response": agent_message,
        "timestamp": timestamp.isoformat() + "Z",
    }


@app.post("/webhook")
async def whatsapp_webhook(request: Request):
    try:
        content_type = request.headers.get("content-type", "")
        if content_type.startswith("application/x-www-form-urlencoded"):
            form = await request.form()
            data = form
        else:
            try:
                data = await request.json()
            except Exception as e:
                print(f"[/webhook] Failed to parse body as JSON: {e}")
                data = {}

        user_id = (data.get("From", "") or "").replace("whatsapp:", "")
        user_message = data.get("Body", "")
        timestamp = datetime.utcnow()
        session_id = f"{user_id}_session"

        media_url = data.get("MediaUrl0")
        media_type = data.get("MediaContentType0", "")

        # Audio flow
        if media_url and isinstance(media_type, str) and media_type.startswith("audio"):
            try:
                import requests  # lazy import
                response = requests.get(media_url, allow_redirects=True)
                if response.status_code in (301, 302, 303, 307, 308):
                    redirect_url = response.headers.get("Location")
                    if redirect_url:
                        response = requests.get(redirect_url)
                response.raise_for_status()
                audio_content = response.content
            except Exception as e:
                print(f"[/webhook] Error downloading media: {e}")
                return respond_twiml_text("Désolé, je n'ai pas pu récupérer l'audio. Réessayez plus tard.")

            # Store user audio message
            await save_chat_message(
                user_id=user_id,
                message="[Audio Message]",  # Placeholder for audio messages
                sender="user",
                timestamp=timestamp,
                audio_url=media_url,
                media_type=media_type,
                session_id=session_id
            )

            try:
                from main import get_agent
                from agno.media import Audio  # lazy import
                agent_response = get_agent().run(
                    "Listen to this audio. Search knowledge base and respond in French using 'vous'.",
                    audio=[Audio(content=audio_content)],
                    user_id=user_id,
                    session_id=session_id
                )
                agent_message = getattr(agent_response, 'content', None) or str(agent_response)
                
                # Store agent response for audio
                await save_chat_message(
                    user_id=user_id,
                    message=agent_message,
                    sender="agent",
                    timestamp=datetime.utcnow(),
                    session_id=session_id
                )
                
                return send_agent_response(user_id, agent_message)
            except Exception:
                import traceback
                print("[/webhook] Agent audio error:\n" + traceback.format_exc())
                error_message = "Désolé, une erreur est survenue avec le traitement audio. Réessayez plus tard."
                
                # Store error response
                await save_chat_message(
                    user_id=user_id,
                    message=error_message,
                    sender="agent",
                    timestamp=datetime.utcnow(),
                    session_id=session_id
                )
                
                return respond_twiml_text(error_message)

        # Text flow
        if user_message:
            # Store user text message
            await save_chat_message(
                user_id=user_id,
                message=user_message,
                sender="user",
                timestamp=timestamp,
                session_id=session_id
            )
        else:
            return FastAPIResponse(content="Missing user_id or message", status_code=200)

        try:
            from main import get_agent
            agent_response = get_agent().run(
                user_message,
                user_id=user_id,
                session_id=session_id
            )
            agent_message = getattr(agent_response, 'content', None) or str(agent_response)
            
            # Store agent response for text
            await save_chat_message(
                user_id=user_id,
                message=agent_message,
                sender="agent",
                timestamp=datetime.utcnow(),
                session_id=session_id
            )
            
            return send_agent_response(user_id, agent_message)
        except Exception:
            import traceback
            print("[/webhook] Agent text error:\n" + traceback.format_exc())
            error_message = "Désolé, une erreur est survenue. Réessayez dans un instant."
            
            # Store error response
            await save_chat_message(
                user_id=user_id,
                message=error_message,
                sender="agent",
                timestamp=datetime.utcnow(),
                session_id=session_id
            )
            
            return respond_twiml_text(error_message)

    except Exception:
        import traceback
        print("[/webhook] Unhandled error:\n" + traceback.format_exc())
        return respond_twiml_text("Désolé, une erreur inattendue est survenue.")


 


if __name__ == "__main__":
    # For local development with Uvicorn (ASGI)
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)


