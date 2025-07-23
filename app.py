import streamlit as st
import httpx
import asyncio
import json

# --- Configuration ---
FASTAPI_URL = "http://127.0.0.1:8000/askllm" # Make sure this matches your FastAPI server's address and port

st.set_page_config(page_title="Streamed LLM Response Demo", layout="wide")

st.title("FastAPI Streamed LLM Response Demo")
st.write("Enter a query and see the LLM response stream in real-time, along with sources if available.")

# --- User Input ---
user_query = st.text_input("Enter your query:", "What is SRVAAU.com about?")
similarity_threshold = st.slider("Similarity Threshold:", min_value=0.0, max_value=1.0, value=0.7, step=0.05)

# --- Stream Button ---
if st.button("Get Streamed Response"):
    if not user_query:
        st.warning("Please enter a query.")
    else:
        st.subheader("LLM Response:")
        answer_placeholder = st.empty() # Placeholder for the streaming answer
        sources_placeholder = st.empty() # Placeholder for sources

        full_answer = []
        
        # Initialize sources_data and response_type in a way they are accessible
        # or manage state within Streamlit. For simplicity, we'll initialize them
        # before the async function and ensure they are read-only from the function
        # or passed as arguments if the function modifies them.
        # However, the previous code intended to modify them.
        # The correct way to modify variables outside the function's scope
        # but not in the global scope (if stream_response was nested) is `nonlocal`.
        # Since it's not nested, they are in the global scope (or module scope in a script).
        # We'll use a container list for `full_answer` and pass sources/response_type as mutable objects
        # or use Streamlit's session_state for proper state management.

        # For this specific error, the issue is that sources_data and response_type were not
        # defined in an *enclosing* scope that stream_response was nested in.
        # They were at the module level.
        # A simple fix if you absolutely need to modify them directly here,
        # without using session_state (which is usually better for Streamlit),
        # is to ensure they are defined in a scope that `nonlocal` can find.
        # Or, just pass them as mutable objects.

        # Let's refactor slightly to avoid `nonlocal` for module-level variables
        # by treating sources_data and response_type as something that will be set
        # by the stream.

        # To handle the error, let's keep track of data using a mutable object like a dictionary
        # or directly setting them as local variables within the `if st.button` block,
        # and then handling their display based on their updated values.
        
        # Reset current display
        answer_placeholder.empty()
        sources_placeholder.empty()

        async def stream_response_logic():
            # These variables will be local to stream_response_logic unless assigned to st.session_state
            # or passed through a mutable container.
            current_full_answer = []
            current_sources_data = None
            current_response_type = "processing..."

            payload = {
                "query": user_query,
                "similarity_threshold": similarity_threshold
            }

            try:
                async with httpx.AsyncClient() as client:
                    async with client.stream("POST", FASTAPI_URL, json=payload, timeout=None) as response:
                        response.raise_for_status() # Raise an exception for bad status codes

                        # Process the stream
                        async for chunk in response.aiter_bytes():
                            decoded_chunk = chunk.decode("utf-8")
                            for line in decoded_chunk.splitlines():
                                if line.strip():
                                    try:
                                        data = json.loads(line)
                                        if "initial_message" in data:
                                            # This is the first chunk with metadata
                                            current_response_type = data.get("response_type", "unknown")
                                            current_sources_data = data.get("sources")
                                            st.info(f"Response Type: **{current_response_type.replace('_', ' ').title()}**")
                                            if current_sources_data:
                                                sources_placeholder.markdown("### Sources:")
                                                for source in current_sources_data:
                                                    sources_placeholder.markdown(
                                                        f"- **[{source['title']}]({source['url']})** "
                                                        f"(Relevance: `{source['relevance_score']:.3f}`)\n"
                                                        f"  Snippet: _{source['text_snippet']}_\n"
                                                    )
                                        elif "text_chunk" in data:
                                            # Append and update the answer
                                            current_full_answer.append(data["text_chunk"])
                                            answer_placeholder.markdown("".join(current_full_answer))
                                        elif "error" in data:
                                            st.error(f"Error from API: {data.get('message', 'Unknown error')}")
                                            break # Stop processing on error
                                    except json.JSONDecodeError:
                                        st.warning(f"Received malformed JSON chunk: {line}")
                                    except Exception as e:
                                        st.error(f"An unexpected error occurred while processing stream: {e}")
                                        break

            except httpx.RequestError as e:
                st.error(f"Network or API connection error: {e}")
            except httpx.HTTPStatusError as e:
                st.error(f"API returned an error {e.response.status_code}: {e.response.text}")
            except Exception as e:
                st.error(f"An unexpected error occurred: {e}")

        # Run the async function using asyncio
        asyncio.run(stream_response_logic())

        st.success("Stream finished!")