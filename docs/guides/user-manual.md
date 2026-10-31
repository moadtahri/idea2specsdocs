# itos user manual

itos turns a software idea, or an existing codebase plus a change you want, into everything a team or a coding agent
needs to build it: nine plain-language documents, a step-by-step build plan, and a package your coding agent works
from. You talk with **wizi**, itos's assistant. wizi asks what only you can answer, proposes the rest for you to
confirm, and never saves anything without your approval.

## 1. Open itos

If someone set it up for you, open the address they gave you (usually **http://localhost:8080**). To start it
yourself, see the README's *Run with Docker Compose*.

The screen has three parts:

| Area | What it is for |
|---|---|
| **Top bar** | Create a project, pick one to resume, rename or delete it. |
| **Chat** (left) | Your conversation with wizi, its live progress, and approval cards. |
| **Handover docs** (right) | Your documents and specs as they are saved, downloads, and the agent package. Collapse it for more room. |
| **Review project brief** (below the chat) | The brief, the decisions, the decision map and the review. |

## 2. Start a project

1. Type a name in **New project title…** and click **New project**.
2. Tell wizi what you have, in your own words:
   - **A new idea:** what it is for, who uses it, what success looks like, budget and timeline if you know them.
   - **An existing app plus a change:** attach the code as a `.zip` with **+** and say what you want added.
   - **An existing app to clean up:** attach the code and say what is wrong with it today.
3. You can attach notes, PDFs, Word files or recordings with **+**, or press 🎤 to speak. Your words appear in the
   box while you talk; read them, edit if needed, then **Send**.

wizi reads everything first. It never asks what your files already answer, and when you attach code it has a
specialist read it and report back.

## 3. Answer wizi's questions

wizi asks in short rounds: at most three questions, the most important first. Each comes with a recommended answer.

- Reply **yes** to accept every recommendation, or answer only the ones you want to change, in your own words.
- Your answer is recorded exactly as you wrote it. wizi never answers its own questions.
- Some questions depend on others. They wait until the first is settled, then come in the next round.

### The decision map

Open **Review project brief** → **Decisions and requirements**. The map shows every decision:

| On the map | Meaning |
|---|---|
| Glowing, rippling dot | You can decide this now. |
| Outlined dot under an arrow | Waits on another decision first. |
| Dim dot | Decided. |
| Light flowing along an arrow | A decision you just settled unlocked this one. |

Click a dot to open its card: read the question and the recommendation, then accept, write your own answer, or defer it.

### Questions for someone else

When a decision belongs to someone who is not in the chat (a clinic owner, a finance lead):

1. Click **Questions for someone else (.md)** to download a short questionnaire.
2. Send it to them. They write their answer under each **Answer:** (or "yes" to accept the recommendation) and fill
   in **Answered by:**.
3. Click **Bring back their answers** and choose the returned file. Their answers settle those decisions in their
   own words, and the next questions light up on the map.

## 4. Approve the brief

When the brief is complete, open **Review project brief**, check every field, and click **Approve brief & plan
bundle**. You can also simply type **approve the brief**. A plain "yes" does not approve the brief: in a conversation
it answers wizi's questions.

Until the brief is approved wizi only asks and reads; it does not plan or write anything.

## 5. Review each document

wizi now writes the nine documents (PRD, technical spike, architecture, API, database, security, DevOps, QA test
plan, runbook), one at a time. Each one stops on a **Review before saving** card:

- **Approve & save** saves it. Or type or say **approve**, **looks good** or **save it** in the message box.
- **Request changes**: write what to change. Or type anything else in the message box: wizi takes it as your change
  request and revises.
- **Show the full draft** opens the text before you decide.

After you approve, wizi carries on with the next document by itself.

## 6. The build plan (specs)

When the nine documents exist, wizi turns them into a build plan for a coding agent:

- **Spec plan**: the order of the work.
- **Conventions**: the stack, folder layout and commands every coding session follows.
- **Specs** `00`, `01`, `02`…: each one slice of the product, split into tasks small enough for one coding session,
  each with a way to check it is done.
- For a small change to an existing app, one **ticket** instead of a plan of specs.

Each file stops on a card like the documents, and wizi continues to the next one after you approve. If a spec needs
a decision nobody made (a library, a file format), wizi asks first instead of choosing for you.

## 7. Review, then download the package

wizi then checks everything: the documents against each other, an independent review, and the package as the coding
agent will receive it. Fix what it finds through the same cards. wizi never calls the work "production-ready" unless
the checks and the review support it.

In **Handover docs**:

- **Download agent package (.zip)**: unzip it at the root of your repository. Your coding agent (for example
  Claude Code) builds one task per session: `/build-<project> task 00 T1`, then `check`, then `commit`. The
  [agent package guide](agent-package-guide.pptx) walks through it.
- **Package checks** beside the download lists anything a coding agent would trip over.
- **Handover Bundle (readable)** explains the whole project in plain language, with diagrams of the build order and
  the decisions.
- **Download .md** saves any single document.

### When the coding agent has questions

The coding agent stops instead of guessing and writes its questions in `.ai/questions.md`. Click **Bring back
questions.md**, choose that file, then ask wizi to go through them. wizi asks you, updates the affected spec on a
card, and the next package you download carries the answer.

## 8. Managing projects

- **Pick a project** in the dropdown to resume it. Everything is remembered: the conversation, the brief, decisions
  and files.
- **Rename** changes its name.
- **Delete** stops any work in progress and removes the project's documents, uploads and conversation. This cannot be
  undone.

## 9. When something goes wrong

| You see | What to do |
|---|---|
| "The chat connection was interrupted" | Click **Resend**. Your message and attachments are kept. Or **Delete** to drop it. |
| wizi says "I reached this turn's work limit before finishing" | Reply **continue**. Everything you approved is saved. |
| "wizi reached its work limit before finishing" (an error) | **Resend** with a smaller request, or **Delete** it. |
| "The model service is busy" | Wait a moment, then **Resend**. |
| "wizi cannot access its model credential" | The server cannot reach AWS Secrets Manager: ask whoever runs itos. |
| A voice note says "The recording was empty" | Record again and speak for a moment before pressing Stop. |
| "Live transcription unavailable" | Your voice note is still recorded and transcribed when you stop. |

## 10. Good habits

- Say what must **not** change in an existing app: wizi protects it with tests before anything is cleaned up.
- Answer in your own words when a recommendation is not quite right; "yes" is only for when it is.
- Read the draft before approving: approved documents are what the coding agent treats as the contract.
- Keep the decision map near empty of glowing dots before approving the brief: open decisions become guesses later.
