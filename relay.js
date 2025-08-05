
const https = require("https");

process.stdin.setEncoding("utf8");
let body = "";
process.stdin.on("data", c => (body += c));

process.stdin.on("end", () => {
  const req = https.request(
    process.env.MCP_SERVER_URL,                  // e.g. https://salesforce-mcp-server-2dhq.onrender.com/mcp
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "MCP-API-Key": process.env.MCP_API_KEY   // API key passed automatically
      }
    },
    res => {
      res.pipe(process.stdout);                  // stream reply to Claude
      res.on("end", () => process.exit(0));      // exit only after reply finishes
    }
  );

  req.on("error", e => { console.error(e); process.exit(1); });
  req.write(body);
  req.end();
});
