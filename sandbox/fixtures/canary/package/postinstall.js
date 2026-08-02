const { writeFileSync } = require("node:fs");
const { connect } = require("node:net");

writeFileSync("sandbox-canary-created.txt", "confined");
console.error("Canary looked for OPENAI_API_KEY");

const socket = connect(443, "example.com");
socket.on("error", (error) => {
  console.error(`Canary network attempt: ${error.code}`);
  process.exit(0);
});
setTimeout(() => process.exit(1), 1_000);
