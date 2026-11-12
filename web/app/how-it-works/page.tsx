// A plain-language explanation for reviewers: the flow of a call, the models used,
// the safeguards, what is real and what is mocked, and the cost estimate.
export const metadata = { title: "How it works | Virtual KAM" };

export default function HowItWorks() {
  return (
    <div className="stack" style={{ maxWidth: 900 }}>
      <div>
        <h1>How it works</h1>
        <p className="muted" style={{ marginTop: 8, maxWidth: "62ch" }}>
          The language model talks and chooses tools. Plain code computes every number and performs every action.
        </p>
      </div>

      <div className="card">
        <h2>One call, start to finish</h2>
        <div className="flow">
          <div><b>Diagnose</b>Before speaking, code compares the two months and ranks the causes in rupees.</div>
          <div><b>Listen and ask</b>Asha states what she found and asks only what the data cannot show.</div>
          <div><b>Propose</b>Code gives her a playbook that fits this seller, biggest problem first.</div>
          <div><b>Act on a yes</b>Code checks the seller's own words for a clear yes to that action, then saves it.</div>
          <div><b>Follow up</b>She books the next call. It opens with what was agreed and what has changed.</div>
          <div><b>Check and review</b>Every rupee figure she spoke is checked against the data. The team can read any call and sign it off.</div>
        </div>
      </div>

      <div className="card">
        <h2>Models and voice technology</h2>
        <div className="scroll">
          <table>
            <thead><tr><th>Layer</th><th>Choice</th><th>Why</th></tr></thead>
            <tbody>
              <tr><td>Audio and agent framework</td><td>LiveKit Agents (WebRTC)</td><td>Real-time and interruptible. One room per call, so calls scale by adding workers.</td></tr>
              <tr><td>Speech to text</td><td>Sarvam Saaras v4</td><td>Built for Indian accents and mixed Hindi-English. Falls back to per-sentence transcription if the live connection drops.</td></tr>
              <tr><td>Language model</td><td>Sarvam 105B, function calling, reasoning off</td><td>Holds the conversation and picks tools. Reasoning is off because it slowed replies.</td></tr>
              <tr><td>Text to speech</td><td>Sarvam Bulbul v4 Flash, v3 as fallback</td><td>Indian voices at low cost.</td></tr>
              <tr><td>Premium voice</td><td>Gemini Live speech to speech</td><td>Selectable per call. If it is unavailable the call runs on Sarvam.</td></tr>
              <tr><td>Numbers and actions</td><td>Python diagnosis engine and tools</td><td>Every figure is traceable and covered by automated tests.</td></tr>
              <tr><td>Data</td><td>Postgres</td><td>Calls, actions, follow-ups and memory. No state lives in the agent.</td></tr>
            </tbody>
          </table>
        </div>
      </div>

      <div className="card">
        <h2>Safeguards that do not rely on the model behaving</h2>
        <div className="scroll">
          <table>
            <thead><tr><th>Safeguard</th><th>What it does</th><th>Why it exists</th></tr></thead>
            <tbody>
              <tr><td>Consent gate</td><td>An action is saved only if the seller's last words clearly agreed to that action. A question is never a yes.</td><td>On a test call a model saved actions the seller never agreed to.</td></tr>
              <tr><td>Undo</td><td>"I did not want that" removes the action and reverses its effect.</td><td>A seller must be able to say no after the fact.</td></tr>
              <tr><td>Figure check</td><td>After each call, every rupee amount spoken is compared with the data and flagged if it matches nothing.</td><td>A model said "6 lakh" when the figure was 2 lakh.</td></tr>
              <tr><td>Playbook</td><td>Code chooses which actions fit this seller, biggest problem first.</td><td>A model offered price cuts to a seller whose pricing was fine.</td></tr>
              <tr><td>Fallbacks</td><td>Transcription and voice each have a second path; a dropped call is recorded and resumed.</td><td>Calls died on a weak network.</td></tr>
            </tbody>
          </table>
        </div>
      </div>

      <div className="two" style={{ marginTop: 0 }}>
        <div className="card">
          <h2>What is real</h2>
          <ul className="clean">
            <li>The voice conversation, in English and Hinglish</li>
            <li>The diagnosis arithmetic and the ranked playbook</li>
            <li>Tool calls, saved actions and follow-ups</li>
            <li>Memory across calls and the team dashboard</li>
            <li>Cost and reply-delay tracking per call</li>
          </ul>
        </div>
        <div className="card">
          <h2>What is mocked</h2>
          <ul className="clean">
            <li>All seller data. The first seller uses the brief's table; the product detail behind it is invented.</li>
            <li>The effect of actions. A restock plan is a saved record, not a purchase order.</li>
            <li>The WhatsApp summary is not sent.</li>
            <li>There is no seller login. Anyone with the link can pick a seller.</li>
          </ul>
        </div>
      </div>

      <div className="card">
        <h2>Assumptions</h2>
        <p style={{ maxWidth: "70ch", marginBottom: 8 }}>The brief gives five numbers for two months. Everything else is an assumption, stated here.</p>
        <ul className="clean" style={{ maxWidth: "80ch" }}>
          <li>Sales are counted before cancellations: in the brief, sales equal orders times the average price in both months.</li>
          <li>The brief's seller has 60 products. Their units and prices are invented, and add up exactly to the brief's sales and orders.</li>
          <li>The loss from stockouts (₹45,450) is measured from those products. The remaining ₹19,550 is inferred to be lost visibility, and labelled that way.</li>
          <li>Visits, rating, rival prices, late dispatch and cancellation reasons are mock values. So are the eleven other sellers.</li>
          <li>The planner assumes stock costs 60% of the selling price. That figure can be changed on the planner page.</li>
          <li>Every recovery figure is an upper limit: it assumes the action works fully for a whole month.</li>
        </ul>
      </div>

      <div className="card">
        <h2>Cost and scale</h2>
        <p style={{ maxWidth: "70ch" }}>
          The default voice costs roughly ₹1.4 to ₹1.8 per call minute at published prices. At one lakh sellers and
          eight call minutes each a month, that is about ₹11 to ₹14 per seller. These are estimates and the system
          has not been load-tested. The nightly scan that flags at-risk sellers uses no language model.
        </p>
      </div>
    </div>
  );
}
