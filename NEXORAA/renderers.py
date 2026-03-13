from rest_framework.renderers import JSONRenderer

class CustomJSONRenderer(JSONRenderer):
    def render(self, data, accepted_media_type=None, renderer_context=None):
        response = renderer_context.get('response') if renderer_context else None
        
        # Fallback if no response context
        if response is None:
            return super().render(data, accepted_media_type, renderer_context)
            
        status_code = response.status_code
        is_success = 200 <= status_code < 400

        # Skip formatting if data is already formatted correctly
        if isinstance(data, dict) and {"status", "message", "data"}.issubset(data.keys()) and len(data.keys()) == 3:
            return super().render(data, accepted_media_type, renderer_context)

        message = ""
        response_data = data

        if isinstance(data, dict):
            # Extract common message keys to use as the top-level message
            if "message" in data and isinstance(data["message"], str):
                message = data["message"]
                response_data = {k: v for k, v in data.items() if k != "message"}
            elif "detail" in data and isinstance(data["detail"], str):
                message = data["detail"]
                response_data = {k: v for k, v in data.items() if k != "detail"}
            elif "error" in data and isinstance(data["error"], str):
                # We grab the error string for the message but we keep it in the dict if needed, 
                # or pop it. Let's pop it for cleaner responses.
                message = data["error"]
                response_data = {k: v for k, v in data.items() if k != "error"}

        if not message:
            message = "Success" if is_success else "An error occurred"

        formatted_data = {
            "status": is_success,
            "message": message,
            "data": response_data if response_data is not None else {}
        }

        return super().render(formatted_data, accepted_media_type, renderer_context)
