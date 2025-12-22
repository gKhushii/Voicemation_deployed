// sample.js
const inputText = process.argv.slice(2).join(" ");

const messages = [
  { role: "system", content: "You are an assistant that takes a user's request and returns an action command like 'run:circle', 'run:square', or 'run:circle_to_square'. Only return one command like that — nothing else." },
  { role: "user", content: inputText }
];

const response = await client.path("/chat/completions").post({
  body: {
    messages,
    temperature: 0.2,
    top_p: 1.0,
    model: model
  }
});

console.log(response.body.choices[0].message.content.trim());
