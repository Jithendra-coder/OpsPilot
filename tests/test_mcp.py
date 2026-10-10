import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

import app
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client


class MCPGatewayTests(unittest.IsolatedAsyncioTestCase):
    async def test_stdio_gateway_exposes_only_bounded_read_tools(self):
        with tempfile.TemporaryDirectory(prefix="opspilot-mcp-") as root:
            previous_data, previous_db = app.DATA, app.DB_PATH
            app.DATA = Path(root)
            app.DB_PATH = app.DATA / "opspilot.db"
            try:
                app.initialize()
                scenario = app.scenarios()[0]
                with app.db() as con:
                    stored = con.execute("SELECT * FROM scenarios WHERE id=?", (scenario["id"],)).fetchone()
                    incident_id = app.add_incident(con, stored["title"], stored["severity"], stored["service_id"],
                        stored["description"], "Test operator", "simulation", stored["id"])

                environment = dict(os.environ, OPSPILOT_DATA_DIR=root)
                parameters = StdioServerParameters(command=sys.executable, args=["-m", "backend.mcp_server"],
                    cwd=app.ROOT, env=environment)
                async with stdio_client(parameters) as (read_stream, write_stream):
                    async with ClientSession(read_stream, write_stream) as client:
                        await client.initialize()
                        result = await client.list_tools()
                        names = {item.name for item in result.tools}
                        self.assertEqual(len(names), 10)
                        self.assertNotIn("execute_action", names)
                        observation = await client.call_tool("get_recent_logs", {"incident_id": incident_id, "limit": 10})
                        payload = json.loads(observation.content[0].text)
                        self.assertTrue(payload["items"])
                        denied = await client.call_tool("get_recent_logs", {"incident_id": incident_id, "service_id": "catalog"})
                        error = json.loads(denied.content[0].text)
                        self.assertEqual(error["error"]["code"], "service_scope_denied")
            finally:
                app.DATA, app.DB_PATH = previous_data, previous_db


if __name__ == "__main__":
    unittest.main()
