import asyncio
import json
from fastmcp import Client
from claude_history_mcp.server import mcp


async def main():
    print("Starting live data integration test against real ~/.claude data...")
    async with Client(mcp) as client:
        print("\n--- 1. Testing list_sessions ---")
        sessions = await client.call_tool("list_sessions", {"limit": 3})
        print(f"Result count: {len(sessions.data)}")
        if sessions.data:
            print("First session:", json.dumps(sessions.data[0], indent=2))
            sample_session_id = sessions.data[0].get("session_id")
        else:
            sample_session_id = None

        print("\n--- 2. Testing search_messages ---")
        msgs = await client.call_tool(
            "search_messages", {"query": "python", "limit": 2}
        )
        print(f"Messages found: {len(msgs.data)}")
        if msgs.data:
            print("Sample match:", json.dumps(msgs.data[0], indent=2))

        print("\n--- 3. Testing search_history ---")
        hist = await client.call_tool("search_history", {"query": "git", "limit": 2})
        print(f"History commands found: {len(hist.data)}")
        if hist.data:
            print("Sample command:", json.dumps(hist.data[0], indent=2))

        print("\n--- 4. Testing get_model_usage ---")
        usage = await client.call_tool("get_model_usage", {"include_totals": True})
        print("Model usage result:", json.dumps(usage.data, indent=2))

        if sample_session_id:
            print(
                f"\n--- 5. Testing get_session_transcript for {sample_session_id} ---"
            )
            transcript = await client.call_tool(
                "get_session_transcript", {"session_id": sample_session_id}
            )
            print(
                "Transcript status/length:",
                type(transcript.data),
                len(transcript.data)
                if isinstance(transcript.data, dict)
                else transcript.data,
            )

            print(f"\n--- 6. Testing get_file_changes for {sample_session_id} ---")
            file_changes = await client.call_tool(
                "get_file_changes", {"session_id": sample_session_id}
            )
            print("File changes result:", json.dumps(file_changes.data, indent=2))

            print(f"\n--- 7. Testing get_tool_inputs for {sample_session_id} ---")
            tool_inputs = await client.call_tool(
                "get_tool_inputs", {"session_id": sample_session_id}
            )
            print(
                "Tool inputs result count:",
                tool_inputs.data.get("count")
                if isinstance(tool_inputs.data, dict)
                else tool_inputs.data,
            )

        print("\n--- 8. Testing search_file_changes ---")
        search_fc = await client.call_tool(
            "search_file_changes", {"file_path": "pyproject.toml"}
        )
        print("Search file changes result:", json.dumps(search_fc.data, indent=2))

        print("\n--- 9. Testing memory_reflect ---")
        reflect_res = await client.call_tool(
            "memory_reflect", {"project": "claude-history-mcp", "query": "architecture"}
        )
        print("Memory reflect result:", json.dumps(reflect_res.data, indent=2))

        print("\n--- 10. Testing health resource ---")
        resources = await client.list_resources()
        print("Resources:", [str(r.uri) for r in resources])
        health = await client.read_resource("claude://health")
        print("Health resource content:\n", health)

    print("\nLive data integration test completed successfully!")


if __name__ == "__main__":
    asyncio.run(main())
