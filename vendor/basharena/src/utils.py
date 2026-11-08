import asyncio
from pathlib import Path
import random
from typing import List, Dict, Any, Optional
import json
import logging
from inspect_ai.model import ModelOutput
from inspect_ai.tool import ContentText

# Set up logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

BASE_ENVIRONMENT_DIR = Path(__file__).parent / "base_environment"


class TqdmLoggingHandler(logging.Handler):
    """Custom logging handler that uses tqdm.write() to avoid interfering with progress bars"""

    def emit(self, record):
        try:
            # Import tqdm here to avoid dependency issues if tqdm is not available
            from tqdm import tqdm

            msg = self.format(record)
            tqdm.write(msg)
        except ImportError:
            # Fall back to regular print if tqdm is not available
            msg = self.format(record)
            print(msg)
        except Exception:
            self.handleError(record)


def setup_tqdm_logging():
    """Configure logging to work with tqdm progress bars"""
    # Get the root logger
    root_logger = logging.getLogger()

    # Remove existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Add our tqdm-compatible handler
    tqdm_handler = TqdmLoggingHandler()
    tqdm_handler.setFormatter(
        logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    )
    root_logger.addHandler(tqdm_handler)
    root_logger.setLevel(logging.INFO)


def make_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


logger = make_logger(__name__)


def load_questions(
    filename: str = "linux_questions.json",
) -> Optional[List[Dict[str, Any]]]:
    """Load questions from JSON file"""
    try:
        with open(filename, "r", encoding="utf-8") as f:
            questions = json.load(f)
        logger.info(f"Loaded {len(questions)} questions from {filename}")
        return questions
    except Exception as e:
        logger.error(f"Error loading questions: {str(e)}")
        return None


def get_model_response_str(model_output: ModelOutput) -> str:
    """Deprecated function from controlarena, copying it here for lazy reasons. Extract the response from the model output as a string.


    Args:
        model_output: Model output


    Returns:
        Model response as a string
    """
    model_response = model_output.message.content
    if isinstance(model_response, list):
        text_responses = [
            part for part in model_response if isinstance(part, ContentText)
        ]
        assert len(text_responses) == 1, (
            f"expected only one response from the model, but got: {text_responses}"
        )
        chosen_response = text_responses[0]
        return chosen_response.text
    else:
        return model_response


async def create_message_streaming(client, max_retries=4, **kwargs):
    """
    Helper function to create a message with streaming while maintaining
    full compatibility with non-streaming API.

    Args:
        client: The API client to use for making requests
        max_retries: Maximum number of retry attempts (default: 4)
        **kwargs: Additional arguments to pass to the API call
    """
    kwargs["stream"] = True

    for attempt in range(max_retries + 1):
        try:
            stream = await client.messages.create(**kwargs)

            # Initialize message structure
            message_content = []
            current_content_block = None
            usage_info = None  # Add usage tracking

            async for event in stream:
                if event.type == "message_start":
                    # Initialize with empty message
                    pass

                elif event.type == "content_block_start":
                    # Start a new content block
                    if event.content_block.type == "text":
                        current_content_block = {"type": "text", "text": ""}
                        message_content.append(current_content_block)
                    elif event.content_block.type == "thinking":
                        current_content_block = {
                            "type": "thinking",
                            "thinking": "",
                            "signature": "",
                        }
                        message_content.append(current_content_block)
                    elif event.content_block.type == "tool_use":
                        current_content_block = {
                            "type": "tool_use",
                            "id": event.content_block.id,
                            "name": event.content_block.name,
                            "input": {},
                        }
                        message_content.append(current_content_block)

                elif event.type == "content_block_delta":
                    if current_content_block is not None:
                        if event.delta.type == "text_delta":
                            current_content_block["text"] += event.delta.text
                        elif event.delta.type == "thinking_delta":
                            current_content_block["thinking"] += event.delta.thinking
                        elif event.delta.type == "signature_delta":
                            current_content_block["signature"] += event.delta.signature
                        elif event.delta.type == "input_json_delta":
                            # Handle tool use input streaming
                            if "partial_json" not in current_content_block:
                                current_content_block["partial_json"] = ""
                            current_content_block["partial_json"] += (
                                event.delta.partial_json
                            )

                elif event.type == "content_block_stop":
                    # Content block is complete - finalize tool use input if needed
                    if (
                        current_content_block
                        and current_content_block.get("type") == "tool_use"
                    ):
                        if "partial_json" in current_content_block:
                            try:
                                current_content_block["input"] = json.loads(
                                    current_content_block["partial_json"]
                                )
                                del current_content_block["partial_json"]
                            except json.JSONDecodeError:
                                # Keep partial JSON if it can't be parsed
                                pass
                    current_content_block = None

                elif event.type == "message_delta":
                    # Capture usage information when available
                    if hasattr(event, "usage") and event.usage:
                        usage_info = event.usage

                elif event.type == "message_stop":
                    # Stream is complete
                    break

                elif event.type == "ping":
                    # Handle ping events
                    continue

                elif event.type == "error":
                    # Handle error events
                    raise Exception(f"Stream error: {event.error}")

            class StreamResponse:
                def __init__(self, content_list, usage=None):
                    self.content = content_list
                    self.usage = usage

            return StreamResponse(message_content, usage_info)

        except Exception as e:
            # If this is the last attempt, re-raise with additional context
            if attempt == max_retries:
                raise Exception(
                    f"Max retries ({max_retries}) exceeded. Last failure: {type(e).__name__}: {str(e)}"
                ) from e

            # Calculate exponential backoff with jitter
            delay = 4 ** (attempt + 1)  # 4s, 16s, 64s, 256s...
            delay *= random.uniform(0.8, 1.2)  # Add up to 20% jitter

            logger.info(
                f"Retrying model call after {int(delay)} seconds due to error: {type(e).__name__}: {str(e)}"
            )

            # Wait before retrying
            await asyncio.sleep(delay)