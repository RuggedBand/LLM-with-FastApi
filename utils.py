import os
import asyncio
import asyncpg
from typing import List, Dict, Any, Optional
from fastapi import HTTPException
from urllib.parse import quote_plus
from dotenv import load_dotenv
import json
from models import RequestStatusResponse

load_dotenv()

DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT")
DB_NAME = os.getenv("DB_NAME")

DATABASE_URL = f"postgresql://{quote_plus(DB_USER)}:{quote_plus(DB_PASSWORD)}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
status_map = { 
    0: "NOT PROCESSED",
    1: "RUNNING",
    2: "SUCCESS",
    3: "FAILED"
}
async def get_db_connection():
    try:
        return await asyncpg.connect(DATABASE_URL)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database connection failed: {e}")

async def get_posts_from_db_async():
    conn = await get_db_connection()
    try:
        query = 'SELECT "Id", "Content", "Title" FROM "Community_Post"'
        records = await conn.fetch(query)
        posts_data = []
        for record in records:
            posts_data.append({
                'Id': record['Id'],
                'Content': record['Content'],
                'Title': record['Title']
            })
        return posts_data
    except Exception as e:
        print(f"Error fetching data from PostgreSQL with asyncpg: {e}")
        raise
    finally:
        if 'conn' in locals() and conn:
            await conn.close()

async def insert_request(request_data: Dict[str, Any]):
    conn = await get_db_connection()
    try:
        await conn.execute('''
            INSERT INTO articlesllm 
            (request_id, user_query, model, name, userid, status, timestamp, result)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        ''', 
        request_data["request_id"],
        request_data["user_query"],
        request_data["model"],
        request_data["name"],
        request_data["userid"],
        request_data["status"],
        request_data["timestamp"],
        request_data.get("result")
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to insert request: {e}")
    finally:
        await conn.close()

async def get_all_requests() -> List[Dict[str, Any]]:
    conn = await get_db_connection()
    try:
        rows = await conn.fetch('SELECT * FROM articlesllm ORDER BY timestamp')
        requests = []
        for row in rows:
            request_dict = dict(row)
            if request_dict.get('timestamp'):
                request_dict['timestamp'] = request_dict['timestamp'].isoformat()
            requests.append(request_dict)
        return requests
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read requests: {e}")
    finally:
        await conn.close()

async def get_request_status_only(request_id: str) -> RequestStatusResponse:
    conn = await get_db_connection()
    try:
        query = 'SELECT * FROM articlesllm WHERE request_id = $1 LIMIT 1'
        row = await conn.fetchrow(query, request_id)

        if not row:
            raise HTTPException(status_code=404, detail=f"No request found with request_id: {request_id}")

        result = row.get('result')
        status_code = row.get('status')
        user_query = row.get('user_query')
        model = row.get('model')
        name = row.get('name')
        userid = row.get('userid')


        return RequestStatusResponse(
            status= status_map.get(status_code, f"UNKNOWN ({status_code})"),
            user_query= user_query,
            model= model,
            name= name,
            userid= userid,
            request_id= request_id,
            timestamp= row.get('timestamp').isoformat() if row.get('timestamp') else None,
            result= json.loads(result) if result else None
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch request status: {e}")
    finally:
        await conn.close()

async def get_requests_by_user_id(user_id: str) -> List[Dict[str, Any]]:
    conn = await get_db_connection()
    
    try:
        query = 'SELECT * FROM articlesllm WHERE userid = $1 ORDER BY timestamp DESC'
        rows = await conn.fetch(query, user_id)
        requests = []
        for row in rows:
            request_dict = dict(row)
            if request_dict.get('timestamp'):
                request_dict['timestamp'] = request_dict['timestamp'].isoformat()

            status_code = request_dict.get('status')
            if status_code in status_map:
                request_dict['status'] = status_map[status_code]

            if request_dict.get('result'):
                try:
                    request_dict['result'] = json.loads(request_dict['result'])
                except Exception as e:
                    request_dict['result'] = {"error": "Failed to decode result JSON", "raw": request_dict['result']}
            
            requests.append(request_dict)
        return requests
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch requests for user_id: {e}")
    finally:
        await conn.close()

async def update_request_if_pending(request_id: str, model: Optional[str], user_query: Optional[str]) -> str:
    conn = await get_db_connection()
    try:
        # Fetch current status
        row = await conn.fetchrow('SELECT status FROM articlesllm WHERE request_id = $1', request_id)
        if not row:
            raise HTTPException(status_code=404, detail=f"Request with id {request_id} not found")

        if row['status'] != 0:
            return "Cannot update: Request is not in NOT PROCESSED state."

        fields = []
        values = []

        if model is not None:
            fields.append('model = $' + str(len(values) + 1))
            values.append(model)

        if user_query is not None:
            fields.append('user_query = $' + str(len(values) + 1))
            values.append(user_query)

        if not fields:
            return "Nothing to update."

        values.append(request_id)
        query = f'''
            UPDATE articlesllm 
            SET {', '.join(fields)} 
            WHERE request_id = ${len(values)}
        '''
        await conn.execute(query, *values)
        return "Updated successfully."
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update request: {e}")
    finally:
        await conn.close()

async def update_request_status(request_id: str, status: int, result: Optional[Dict[str, Any]] = None):
    conn = await get_db_connection()
    try:
        if result is not None:
            await conn.execute('''
                UPDATE articlesllm 
                SET status = $1, result = $2 
                WHERE request_id = $3
            ''', status, result, request_id)
        else:
            await conn.execute('''
                UPDATE articlesllm 
                SET status = $1 
                WHERE request_id = $2
            ''', status, request_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update request status: {e}")
    finally:
        await conn.close()

async def get_pending_requests() -> List[Dict[str, Any]]:
    conn = await get_db_connection()
    try:
        rows = await conn.fetch('SELECT * FROM articlesllm WHERE status = 0 ORDER BY timestamp')
        requests = []
        for row in rows:
            request_dict = dict(row)
            if request_dict.get('timestamp'):
                request_dict['timestamp'] = request_dict['timestamp'].isoformat()
            requests.append(request_dict)
        return requests
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get pending requests: {e}")
    finally:
        await conn.close()

async def get_pending_requests_count() -> int:
    conn = await get_db_connection()
    try:
        count = await conn.fetchval('SELECT COUNT(*) FROM articlesllm WHERE status = 0')
        return count or 0
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get pending requests count: {e}")
    finally:
        await conn.close()

async def delete_request_by_id(request_id: str) -> str:
    conn = await get_db_connection()
    try:
        # First, check the current status of the request
        row = await conn.fetchrow('SELECT status FROM articlesllm WHERE request_id = $1', request_id)

        if not row:
            raise HTTPException(status_code=404, detail=f"No request found with ID {request_id}.")

        current_status = row['status']

        # Only proceed with deletion if the status is 0 (NOT PROCESSED)
        if current_status == 0:
            command_status = await conn.execute('DELETE FROM articlesllm WHERE request_id = $1', request_id)
            if command_status == 'DELETE 1':
                return f"Request with ID {request_id} deleted successfully."
            else:
                # This case should ideally not be reached if row was found and status was 0
                raise HTTPException(status_code=500, detail=f"Failed to delete request with ID {request_id} despite status being 0.")
        else:
            raise HTTPException(status_code=400, detail=f"Cannot delete request with ID {request_id}. Its status is '{status_map.get(current_status, 'UNKNOWN')}' (only 'NOT PROCESSED' status can be deleted).")

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete request: {e}")
    finally:
        await conn.close()