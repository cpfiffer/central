import { createSession } from "@letta-ai/letta-code-sdk";

async function main() {
  console.log("Creating session...");
  
  const session = createSession("agent-c770d1c8-510e-4414-be36-c9ebd95a7758", {
    permissionMode: "bypassPermissions",
    cwd: "/home/cameron/central/handlers",
    newConversation: true,
  });

  console.log("Sending message...");
  await session.send("Say hello in one word. Just the word, nothing else.");
  console.log("Message sent, streaming...");
  
  let response = "";
  for await (const msg of session.stream()) {
    console.log("MSG:", msg.type, JSON.stringify(msg).slice(0, 150));
    if (msg.type === "assistant") {
      response += msg.content;
    }
    if (msg.type === "result") break;
  }
  
  console.log("Response:", response);
  session.close();
  console.log("Done");
  process.exit(0);
}

setTimeout(() => { console.log("GLOBAL TIMEOUT"); process.exit(1); }, 120000);
main().catch(e => { console.error("FATAL:", e); process.exit(1); });
