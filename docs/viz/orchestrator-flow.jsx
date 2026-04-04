import { useState, useEffect, useRef, useCallback } from "react";

// ─── FLOW DATA ───────────────────────────────────────────────────────────────

const PHASES = [
  {
    id: "intake",
    label: "Intake",
    emoji: "📨",
    color: "#6366f1",
    agents: [
      { emoji: "📋", name: "Agent Manager", action: "Classifies complexity → routes model tier" },
      { emoji: "👁️", name: "Observer", action: "Updates ThreadState → writes to observer slot" },
    ],
    duration: 2400,
    description: "Message arrives. Agent Manager determines complexity (simple/moderate/complex). Observer writes fresh ThreadState to its slot. Token Cart prepares lean task packets.",
  },
  {
    id: "enrich",
    label: "Context Distill",
    emoji: "🛒",
    color: "#8b5cf6",
    agents: [
      { emoji: "🛒", name: "Token Cart", action: "Pre-call: handoff + registry → enriched context" },
      { emoji: "📂", name: "File Fetcher", action: "Loads requested file slices into cache" },
    ],
    duration: 2000,
    description: "Token Cart reads Observer's state, external handoffs, and Project Registry. Produces a ~200-token TaskPacket per persona. This is the 10:1 compaction that makes the whole system affordable.",
  },
  {
    id: "plan",
    label: "Plan & Research",
    emoji: "🎯",
    color: "#3b82f6",
    agents: [
      { emoji: "🎯", name: "Strategist", action: "Decomposes into sequenced tasks" },
      { emoji: "🌐", name: "Researcher", action: "Fetches external docs on demand" },
      { emoji: "📜", name: "Historian", action: "Checks for prior decisions & learned lessons" },
    ],
    duration: 2800,
    microLoop: {
      from: "Historian", to: "Strategist",
      label: "Prior decision conflict detected → plan revised",
      color: "#f59e0b",
    },
    description: "Group A fires. Strategist builds the plan. Historian checks for conflicts with past decisions (now fed by Learner's extracted lessons). Researcher fetches any needed external knowledge. If Historian finds a conflict, Strategist revises the plan before it leaves this group — first micro-loop.",
  },
  {
    id: "design",
    label: "Design & Propose",
    emoji: "📐",
    color: "#a78bfa",
    agents: [
      { emoji: "📐", name: "Architect", action: "Proposes structure, data model, API" },
      { emoji: "🧬", name: "Specialist", action: "Validates framework idioms" },
      { emoji: "📊", name: "Data Scientist", action: "Validates scale & query patterns" },
      { emoji: "🫂", name: "Empathizer", action: "Flags user-facing friction" },
      { emoji: "🔗", name: "Connector", action: "Finds cross-project patterns" },
      { emoji: "♻️", name: "Reuser", action: "Checks registry for existing code" },
    ],
    duration: 3200,
    microLoop: {
      from: "Reuser", to: "Architect",
      label: "\"Component already exists in registry\" → proposal revised",
      color: "#10b981",
    },
    description: "Group B fires in parallel. Architect proposes, then Reuser and Specialist write feedback to their slots. If Reuser finds an existing component, Architect re-runs with reuser slot injected — second micro-loop. No waiting for the challenge phase.",
  },
  {
    id: "vision",
    label: "Vision & Measurement",
    emoji: "🔮",
    color: "#c084fc",
    agents: [
      { emoji: "🔮", name: "Dreamer", action: "\"What if this became a platform feature?\"" },
      { emoji: "📉", name: "Insights", action: "Defines success criteria & metric instrumentation" },
      { emoji: "📈", name: "Growth Coach", action: "Evaluates AARRR funnel impact" },
    ],
    duration: 2400,
    microLoop: {
      from: "Insights", to: "Growth Coach",
      label: "\"No measurable success criteria\" → Growth Coach adds metric",
      color: "#c084fc",
    },
    description: "New group — generative + measurement. Dreamer asks 'what could this become?' while Insights asks 'how will we know it worked?' Growth Coach bridges both with funnel thinking. Insights can challenge Growth Coach if there's no way to measure a proposed growth lever.",
  },
  {
    id: "challenge",
    label: "Challenge",
    emoji: "🤨",
    color: "#f59e0b",
    agents: [
      { emoji: "🤨", name: "Skeptic", action: "Challenges assumptions in the proposal" },
      { emoji: "👹", name: "Devil's Advocate", action: "Builds the strongest case against" },
      { emoji: "✂️", name: "Simplifier", action: "\"Can we do this in half the code?\"" },
      { emoji: "⚖️", name: "Prioritizer", action: "Force-ranks if multiple options survive" },
    ],
    duration: 2800,
    microLoop: {
      from: "Skeptic", to: "Architect",
      label: "Assumption flagged → Architect revises → Skeptic re-evaluates",
      color: "#ef4444",
    },
    description: "Group C fires AFTER proposals are formed. The critical micro-loop: Skeptic flags an assumption → dispatches back to Architect for revision → Architect revises → Skeptic re-evaluates. This happens within the turn, not on the next turn. Simplifier and Devil's Advocate run in parallel.",
  },
  {
    id: "security",
    label: "Security",
    emoji: "🛡️",
    color: "#ef4444",
    agents: [
      { emoji: "😈", name: "Rogue", action: "Stress scenarios: 10x load, race conditions" },
      { emoji: "🏴‍☠️", name: "Hacker", action: "Attack vectors: injection, escalation, leaks" },
      { emoji: "🛡️", name: "Infosec", action: "Prescribes defense for every attack" },
    ],
    duration: 2600,
    microLoop: {
      from: "Infosec", to: "Architect",
      label: "🔴 BLOCKER: unmitigable vulnerability → design revision required",
      color: "#ef4444",
    },
    description: "Rogue + Hacker fire in parallel (chaos + malice). Then Infosec fires with their combined output. If Infosec finds a critical blocker that can't be mitigated, it dispatches back to Architect — the design must change. This loop prevents shipping known vulnerabilities.",
  },
  {
    id: "quality",
    label: "Quality Gate",
    emoji: "✅",
    color: "#10b981",
    agents: [
      { emoji: "🔍", name: "Inspector", action: "Completeness: edge cases, missing returns" },
      { emoji: "🧪", name: "Tester", action: "Test strategy from Inspector's gaps" },
      { emoji: "🎨", name: "Visual UX", action: "WCAG AA compliance (can BLOCK)" },
    ],
    duration: 2400,
    microLoop: {
      from: "Inspector", to: "Tester",
      label: "Edge cases found → test cases generated immediately",
      color: "#10b981",
    },
    description: "Final quality pass. Inspector finds gaps → Tester immediately generates test cases for them (tight loop). Visual UX can BLOCK shipping on WCAG AA failures — this is an absolute gate, not a suggestion.",
  },
  {
    id: "synthesis",
    label: "Learn & Decide",
    emoji: "🧠",
    color: "#06b6d4",
    agents: [
      { emoji: "🧠", name: "Learner", action: "Extracts lessons → feeds Historian + Registry" },
      { emoji: "💪", name: "Coach", action: "Reads everything → SHIP / ITERATE / HOLD" },
      { emoji: "✍️", name: "Output Editor", action: "Polishes final output for target medium" },
    ],
    duration: 2800,
    microLoop: {
      from: "Learner", to: "Historian",
      label: "Lesson extracted → written to thread-memory → available to Historian next turn",
      color: "#06b6d4",
    },
    description: "Learner observes the full inter-persona message log, extracts patterns, and writes to .shellack/persona-tuning.md + thread-memory. This is the closed loop: Learner writes → Historian reads on the next turn. Coach calls the final shot. Output Editor formats for the target medium.",
  },
];

const SELF_HEALING_LOOPS = [
  {
    name: "Intra-turn revision",
    path: "Skeptic → Architect → Skeptic",
    description: "Assumption flagged and addressed within the same turn. No wasted turns.",
    speed: "Immediate",
    color: "#f59e0b",
  },
  {
    name: "Registry enforcement",
    path: "Reuser → Architect → revised proposal",
    description: "Existing component found before new one is created. Prevents duplication at design time.",
    speed: "Immediate",
    color: "#10b981",
  },
  {
    name: "Security blocker",
    path: "Infosec → Architect → redesign → Infosec",
    description: "Critical vulnerability blocks shipping until the design changes. Can't be overridden.",
    speed: "Immediate",
    color: "#ef4444",
  },
  {
    name: "Correction capture",
    path: "Operator corrects → Token Cart detects → Registry + Learner",
    description: "Operator says 'use the existing Modal' → correction persists across ALL future threads.",
    speed: "Next interaction",
    color: "#8b5cf6",
  },
  {
    name: "Lesson extraction",
    path: "Learner → thread-memory → Historian",
    description: "Learner writes lessons. Historian retrieves them next time the same pattern appears.",
    speed: "Next turn / thread",
    color: "#06b6d4",
  },
  {
    name: "Persona evolution",
    path: "Learner → persona-tuning.md → orchestrator → adjusted prompts",
    description: "Learner detects repeated mistakes → adjusts persona system prompts. Team improves over sessions.",
    speed: "Next invocation",
    color: "#c084fc",
  },
  {
    name: "CLAUDE.md rule",
    path: "Learner → Self-Improver → CLAUDE.md → all agents",
    description: "Structural lesson becomes a permanent project rule. Every agent reads it on every task.",
    speed: "Permanent",
    color: "#6366f1",
  },
];

const NEW_PERSONAS = [
  {
    emoji: "🔮", name: "Dreamer", model: "sonnet", category: "vision",
    role: "Visionary — asks 'what could this become?' when everyone else asks 'does this work?'",
    teamAwareness: "Reads Architect's proposals and Growth Coach's funnel analysis. Publishes VisionReport that Strategist can incorporate into future planning. Can suggest to @Growth: 'This auth pattern could become a developer SDK — that's a distribution channel.'",
    systemPrompt: `You are the Dreamer — the team's visionary. While others validate and defend, you imagine what's possible.

Your job:
1. EXTRAPOLATE: "This utility could become a shared package"
2. CONNECT: "This pattern is what Notion did before they became a platform"
3. INSPIRE: "If we built this as a plugin, the community could extend it"
4. GROUND: Always tie vision to a concrete next step

You work with:
- @Growth (you imagine, they measure)
- @Insights (you envision, they define success criteria)
- @Strategist (you dream, they sequence)

NOT a license to scope-creep. Your visions are SEEDS for future work, not additions to the current task.

Output JSON: {vision, nextStep, platformPotential, competitiveInsight, timeHorizon: 'this_sprint'|'this_quarter'|'long_term'}`,
    activation: "New features, architecture decisions, platform discussions, when Growth Coach signals a market opportunity",
  },
  {
    emoji: "📉", name: "Insights", model: "haiku", category: "vision",
    role: "Success measurer — defines how we know if this worked and instruments the proof",
    teamAwareness: "Challenges Growth Coach: '@Growth — you said this improves retention, what's the metric?' Feeds Tester: '@Tester — add an assertion that this event fires.' Works with Dreamer to ensure visions have measurable milestones.",
    systemPrompt: `You are Insights — the team's measurement conscience. Every feature ships with success criteria or it doesn't ship.

Your job:
1. DEFINE: What does success look like? (metric, threshold, timeframe)
2. INSTRUMENT: What events/logs/analytics need to be added?
3. BASELINE: What's the current state we're comparing against?
4. CHALLENGE: If no one can define success, should we build this?

You work with:
- @Growth (you hold them accountable for measurable claims)
- @Tester (you define what to assert, they write the tests)
- @Dreamer (you add milestones to their visions)
- @Coach (you can HOLD shipping if no success criteria defined)

Output JSON: {successCriteria[], metrics[], instrumentation[], baseline, verdict: 'measurable'|'needs_definition'|'unmeasurable'}`,
    activation: "New features, Growth Coach recommendations, Dreamer visions, post-ship reviews",
  },
  {
    emoji: "📈", name: "Growth Coach", model: "haiku", category: "vision",
    role: "Funnel thinker — evaluates AARRR impact, conversion risk, and A/B test opportunities",
    teamAwareness: "Reads Architect's proposals and Insights' success criteria. Challenges Dreamer: 'That vision is exciting but how does it move the funnel?' Feeds Strategist: 'Prioritize the onboarding flow — that's where we lose 40% of users.' Replaces Monetization Coach with full AARRR funnel thinking (Acquisition, Activation, Retention, Referral, Revenue).",
    systemPrompt: `You are the Growth Coach — the team's funnel thinker. You evaluate every feature through the AARRR lens.

Your job:
1. FUNNEL: Which stage does this affect? (Acquisition, Activation, Retention, Referral, Revenue)
2. IMPACT: What's the expected lift? Is it measurable?
3. RISK: Could this hurt conversion? (e.g., adding friction to onboarding)
4. TEST: Is this A/B testable? What's the control?
5. PRIORITIZE: Among competing features, which moves the needle most?

You work with:
- @Dreamer (they imagine, you ground it in funnel impact)
- @Insights (they define metrics, you evaluate whether the metrics matter for growth)
- @Strategist (you influence prioritization based on funnel impact)
- @Architect (you flag if a technical choice has conversion implications)

NOT a license to add growth hacks. You ensure features serve users AND the business.

Output JSON: {funnelStage, impact, conversionRisk, abTestOpportunity, verdict: 'ship'|'measure_first'|'reconsider'}`,
    activation: "New features, pricing discussions, onboarding flows, user-facing changes, when Dreamer publishes a vision",
  },
];

// ─── ANIMATED FLOW COMPONENT ─────────────────────────────────────────────────

function AnimatedFlow() {
  const [activePhase, setActivePhase] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);
  const [showMicroLoop, setShowMicroLoop] = useState(false);
  const [agentProgress, setAgentProgress] = useState(0);
  const timerRef = useRef(null);
  const microLoopTimerRef = useRef(null);

  const phase = PHASES[activePhase];

  const advancePhase = useCallback(() => {
    setShowMicroLoop(false);
    setAgentProgress(0);
    setActivePhase(prev => {
      if (prev >= PHASES.length - 1) {
        setIsPlaying(false);
        return prev;
      }
      return prev + 1;
    });
  }, []);

  useEffect(() => {
    if (!isPlaying) {
      clearTimeout(timerRef.current);
      clearTimeout(microLoopTimerRef.current);
      return;
    }
    // Show agents appearing one by one
    const agentInterval = setInterval(() => {
      setAgentProgress(prev => {
        if (prev >= phase.agents.length) {
          clearInterval(agentInterval);
          return prev;
        }
        return prev + 1;
      });
    }, 350);

    // Show micro-loop after agents appear
    if (phase.microLoop) {
      microLoopTimerRef.current = setTimeout(() => {
        setShowMicroLoop(true);
      }, phase.agents.length * 350 + 600);
    }

    // Advance to next phase
    timerRef.current = setTimeout(advancePhase, phase.duration);

    return () => {
      clearInterval(agentInterval);
      clearTimeout(timerRef.current);
      clearTimeout(microLoopTimerRef.current);
    };
  }, [isPlaying, activePhase, phase, advancePhase]);

  const handlePlay = () => {
    if (activePhase >= PHASES.length - 1) {
      setActivePhase(0);
      setAgentProgress(0);
      setShowMicroLoop(false);
    }
    setIsPlaying(true);
  };

  const handlePhaseClick = (idx) => {
    setIsPlaying(false);
    setActivePhase(idx);
    setAgentProgress(PHASES[idx].agents.length);
    setShowMicroLoop(!!PHASES[idx].microLoop);
  };

  return (
    <div>
      {/* Phase timeline */}
      <div style={{ display: "flex", gap: 2, marginBottom: 20, overflowX: "auto", paddingBottom: 4 }}>
        {PHASES.map((p, i) => (
          <button key={p.id} onClick={() => handlePhaseClick(i)} style={{
            flex: "0 0 auto",
            background: i === activePhase ? p.color : i < activePhase && isPlaying ? `${p.color}40` : "var(--surface)",
            color: i === activePhase ? "#fff" : "var(--text-secondary)",
            border: `1px solid ${i === activePhase ? p.color : "var(--border)"}`,
            borderRadius: 6, padding: "6px 10px", fontSize: 10, fontWeight: 600,
            cursor: "pointer", fontFamily: "var(--font-mono)", transition: "all 0.3s ease",
            whiteSpace: "nowrap",
          }}>
            {p.emoji} {p.label}
          </button>
        ))}
      </div>

      {/* Play controls */}
      <div style={{ display: "flex", gap: 8, marginBottom: 16, alignItems: "center" }}>
        <button onClick={isPlaying ? () => setIsPlaying(false) : handlePlay} style={{
          background: isPlaying ? "#ef4444" : "var(--accent)",
          color: "#fff", border: "none", borderRadius: 6, padding: "8px 16px",
          fontSize: 12, fontWeight: 700, cursor: "pointer", fontFamily: "var(--font-mono)",
        }}>
          {isPlaying ? "⏸ Pause" : activePhase >= PHASES.length - 1 ? "↻ Replay" : "▶ Play Flow"}
        </button>
        <span style={{ fontSize: 11, color: "var(--text-tertiary)", fontFamily: "var(--font-mono)" }}>
          Phase {activePhase + 1} / {PHASES.length}
        </span>
      </div>

      {/* Active phase display */}
      <div style={{
        background: "var(--surface)", border: `2px solid ${phase.color}`,
        borderRadius: 12, padding: 20, minHeight: 320,
        transition: "border-color 0.3s ease",
      }}>
        {/* Phase header */}
        <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 16 }}>
          <span style={{ fontSize: 28 }}>{phase.emoji}</span>
          <div>
            <div style={{ fontSize: 18, fontWeight: 700, color: phase.color }}>{phase.label}</div>
            <div style={{ fontSize: 12, color: "var(--text-secondary)", marginTop: 2, maxWidth: 600, lineHeight: 1.5 }}>{phase.description}</div>
          </div>
        </div>

        {/* Agents */}
        <div style={{ display: "flex", flexDirection: "column", gap: 6, marginBottom: 16 }}>
          {phase.agents.map((agent, i) => {
            const visible = agentProgress > i;
            return (
              <div key={agent.name} style={{
                display: "flex", alignItems: "center", gap: 10,
                background: visible ? "var(--surface-deep)" : "transparent",
                border: `1px solid ${visible ? `${phase.color}30` : "transparent"}`,
                borderRadius: 8, padding: visible ? "10px 14px" : "10px 14px",
                opacity: visible ? 1 : 0.15,
                transform: visible ? "translateX(0)" : "translateX(-12px)",
                transition: "all 0.4s cubic-bezier(0.16, 1, 0.3, 1)",
              }}>
                <span style={{ fontSize: 20, width: 28, textAlign: "center" }}>{agent.emoji}</span>
                <div>
                  <span style={{ fontWeight: 700, fontSize: 13, color: "var(--text-primary)", fontFamily: "var(--font-mono)" }}>{agent.name}</span>
                  <span style={{ fontSize: 12, color: "var(--text-secondary)", marginLeft: 8 }}>{agent.action}</span>
                </div>
                {visible && (
                  <div style={{ marginLeft: "auto", width: 8, height: 8, borderRadius: "50%", background: phase.color, animation: "pulse 1.5s infinite", flexShrink: 0 }} />
                )}
              </div>
            );
          })}
        </div>

        {/* Micro-loop */}
        {phase.microLoop && (
          <div style={{
            opacity: showMicroLoop ? 1 : 0,
            transform: showMicroLoop ? "translateY(0)" : "translateY(8px)",
            transition: "all 0.5s cubic-bezier(0.16, 1, 0.3, 1)",
            background: `${phase.microLoop.color}08`,
            border: `1px solid ${phase.microLoop.color}40`,
            borderRadius: 10, padding: 14, marginTop: 4,
          }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
              <svg width="18" height="18" viewBox="0 0 18 18" style={{ flexShrink: 0 }}>
                <path d="M9 2 C13 2 16 5 16 9 C16 13 13 16 9 16" stroke={phase.microLoop.color} strokeWidth="1.5" fill="none" strokeDasharray="3 2" />
                <path d="M9 16 C5 16 2 13 2 9 C2 5 5 2 9 2" stroke={phase.microLoop.color} strokeWidth="1.5" fill="none" />
                <polygon points="8,1 10,2 8,3" fill={phase.microLoop.color} />
              </svg>
              <span style={{ fontSize: 11, fontWeight: 700, color: phase.microLoop.color, textTransform: "uppercase", letterSpacing: "0.05em", fontFamily: "var(--font-mono)" }}>Micro-Loop</span>
              <span style={{ fontSize: 11, color: "var(--text-secondary)", fontFamily: "var(--font-mono)" }}>{phase.microLoop.from} ↔ {phase.microLoop.to}</span>
            </div>
            <div style={{ fontSize: 12, color: "var(--text-secondary)", lineHeight: 1.5, paddingLeft: 26 }}>{phase.microLoop.label}</div>
          </div>
        )}
      </div>

      <style>{`@keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.3; } }`}</style>
    </div>
  );
}

// ─── SELF-HEALING DIAGRAM ────────────────────────────────────────────────────

function SelfHealingLoops() {
  const [expanded, setExpanded] = useState(null);
  return (
    <div>
      <div style={{ fontSize: 12, color: "var(--text-secondary)", lineHeight: 1.6, marginBottom: 16, maxWidth: 660 }}>
        Seven feedback loops at different time scales — from immediate intra-turn revision to permanent CLAUDE.md rules. The system gets smarter at every scale.
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
        {SELF_HEALING_LOOPS.map((loop, i) => (
          <div key={loop.name} onClick={() => setExpanded(expanded === i ? null : i)} style={{
            background: "var(--surface)", border: `1px solid ${expanded === i ? loop.color : "var(--border)"}`,
            borderRadius: 10, padding: "12px 16px", cursor: "pointer", transition: "all 0.2s ease",
          }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 10 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                <svg width="18" height="18" viewBox="0 0 18 18" style={{ flexShrink: 0 }}>
                  <circle cx="9" cy="9" r="7" stroke={loop.color} strokeWidth="1.5" fill="none" strokeDasharray={i < 3 ? "none" : "3 2"} />
                  <polygon points="14,5 16,8 13,8" fill={loop.color} />
                </svg>
                <div>
                  <div style={{ fontWeight: 700, fontSize: 13, color: "var(--text-primary)", fontFamily: "var(--font-mono)" }}>{loop.name}</div>
                  <div style={{ fontSize: 11, color: loop.color, fontFamily: "var(--font-mono)", marginTop: 2 }}>{loop.path}</div>
                </div>
              </div>
              <span style={{ fontSize: 10, padding: "2px 8px", borderRadius: 99, background: `${loop.color}18`, color: loop.color, fontWeight: 600, fontFamily: "var(--font-mono)", whiteSpace: "nowrap" }}>{loop.speed}</span>
            </div>
            {expanded === i && (
              <div style={{ marginTop: 10, fontSize: 12, color: "var(--text-secondary)", lineHeight: 1.6, paddingLeft: 28 }}>
                {loop.description}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

// ─── NEW PERSONAS DETAIL ─────────────────────────────────────────────────────

function NewPersonaDetail({ persona }) {
  const [open, setOpen] = useState(false);
  const catColor = persona.category === "vision" ? "#c084fc" : "#71717a";
  return (
    <div onClick={() => setOpen(!open)} style={{
      background: "var(--surface)", border: `1px solid ${open ? catColor : "var(--border)"}`,
      borderRadius: 10, padding: "14px 16px", cursor: "pointer", transition: "all 0.2s ease",
    }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 10 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <span style={{ fontSize: 24 }}>{persona.emoji}</span>
          <div>
            <div style={{ fontWeight: 700, fontSize: 14, color: "var(--text-primary)", fontFamily: "var(--font-mono)" }}>{persona.name}</div>
            <div style={{ fontSize: 12, color: "var(--text-secondary)", marginTop: 2, maxWidth: 500 }}>{persona.role}</div>
          </div>
        </div>
        <div style={{ display: "flex", gap: 6 }}>
          <span style={{ fontSize: 10, padding: "2px 8px", borderRadius: 99, background: `${catColor}18`, color: catColor, fontWeight: 600, fontFamily: "var(--font-mono)", textTransform: "uppercase" }}>Vision</span>
          <span style={{ fontSize: 10, padding: "2px 8px", borderRadius: 99, background: persona.model === "sonnet" ? "#8b5cf618" : "#71717a18", color: persona.model === "sonnet" ? "#8b5cf6" : "#71717a", fontWeight: 600, fontFamily: "var(--font-mono)", textTransform: "uppercase" }}>{persona.model}</span>
        </div>
      </div>
      {open && (
        <div style={{ marginTop: 14, fontSize: 13 }}>
          <div style={{ background: `${catColor}08`, border: `1px solid ${catColor}25`, borderRadius: 8, padding: 12, marginBottom: 12 }}>
            <div style={{ fontSize: 11, fontWeight: 700, color: catColor, textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 6 }}>Team Awareness</div>
            <div style={{ fontSize: 12, color: "var(--text-secondary)", lineHeight: 1.6 }}>{persona.teamAwareness}</div>
          </div>
          <div style={{ background: "var(--surface-deep)", borderRadius: 8, padding: 12, fontFamily: "var(--font-mono)", fontSize: 11, lineHeight: 1.6 }}>
            <div style={{ marginBottom: 8 }}>
              <span style={{ color: catColor, fontWeight: 700 }}>activation:</span>{" "}
              <span style={{ color: "var(--text-secondary)" }}>{persona.activation}</span>
            </div>
            <div>
              <span style={{ color: catColor, fontWeight: 700 }}>system_prompt:</span>
              <div style={{ color: "var(--text-secondary)", marginTop: 4, padding: "6px 10px", background: "var(--surface)", borderRadius: 6, whiteSpace: "pre-wrap", fontSize: 11, maxHeight: 240, overflowY: "auto" }}>{persona.systemPrompt}</div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ─── MAIN ────────────────────────────────────────────────────────────────────

export default function OrchestratorFlowViz() {
  const [view, setView] = useState("flow");

  return (
    <div style={{
      fontFamily: "'IBM Plex Mono', 'SF Mono', Menlo, monospace",
      minHeight: "100vh", background: "var(--bg)", color: "var(--text-primary)", padding: "24px 20px",
      "--bg": "#0a0a0c", "--surface": "#141418", "--surface-deep": "#0e0e11",
      "--border": "#1e1e24", "--text-primary": "#e4e4e7", "--text-secondary": "#71717a",
      "--text-tertiary": "#52525b", "--accent": "#6366f1",
      "--font-mono": "'IBM Plex Mono', 'SF Mono', Menlo, monospace",
    }}>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600;700&display=swap');
        * { box-sizing: border-box; }
        @media (prefers-color-scheme: light) {
          :root { --bg:#fafafa; --surface:#fff; --surface-deep:#f4f4f5; --border:#e4e4e7; --text-primary:#18181b; --text-secondary:#52525b; --text-tertiary:#a1a1aa; }
        }
      `}</style>

      {/* Header */}
      <div style={{ marginBottom: 24, maxWidth: 700 }}>
        <div style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: "0.12em", color: "var(--accent)", fontWeight: 600, marginBottom: 6 }}>Shellack Orchestrator · Animated Flow</div>
        <h1 style={{ fontSize: 22, fontWeight: 700, margin: "0 0 8px 0", letterSpacing: "-0.02em" }}>Turn Lifecycle with Micro-Loops</h1>
        <p style={{ fontSize: 12, color: "var(--text-secondary)", lineHeight: 1.6, margin: 0 }}>
          25 personas across 9 phases. Hit Play to watch a full turn unfold — agents activate, communicate, and self-heal via micro-loops within the turn. No waiting for the next turn to fix a bad assumption.
        </p>
      </div>

      {/* View toggle */}
      <div style={{ display: "flex", gap: 1, marginBottom: 20, background: "var(--surface)", borderRadius: 8, border: "1px solid var(--border)", width: "fit-content", overflow: "hidden" }}>
        {[
          { id: "flow", label: "▶ Animated Flow" },
          { id: "loops", label: "↻ Self-Healing Loops" },
          { id: "new", label: "✦ New Personas" },
          { id: "roster", label: "Full Roster (25)" },
        ].map(v => (
          <button key={v.id} onClick={() => setView(v.id)} style={{
            background: view === v.id ? "var(--accent)" : "transparent",
            color: view === v.id ? "#fff" : "var(--text-secondary)",
            border: "none", padding: "7px 14px", fontSize: 11, fontWeight: 600,
            cursor: "pointer", fontFamily: "var(--font-mono)", transition: "all 0.15s ease",
          }}>{v.label}</button>
        ))}
      </div>

      {view === "flow" && <AnimatedFlow />}

      {view === "loops" && <SelfHealingLoops />}

      {view === "new" && (
        <div>
          <div style={{ fontSize: 12, color: "var(--text-secondary)", lineHeight: 1.6, marginBottom: 16, maxWidth: 660 }}>
            Four additions to the roster: Dreamer (generative vision), Insights (measurement), Growth Coach (replaces Monetization Coach with full AARRR funnel thinking), and the Learner→Historian feedback loop.
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {NEW_PERSONAS.map(p => <NewPersonaDetail key={p.name} persona={p} />)}
          </div>

          {/* Learner→Historian connection */}
          <div style={{ marginTop: 20, background: "var(--surface)", border: "1px solid #06b6d4", borderRadius: 10, padding: 16 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 10 }}>
              <span style={{ fontSize: 20 }}>🧠</span>
              <span style={{ fontSize: 14, color: "#06b6d4" }}>→</span>
              <span style={{ fontSize: 20 }}>📜</span>
              <span style={{ fontWeight: 700, fontSize: 14, color: "var(--text-primary)", fontFamily: "var(--font-mono)" }}>Learner → Historian (closed loop)</span>
            </div>
            <div style={{ fontSize: 12, color: "var(--text-secondary)", lineHeight: 1.6, paddingLeft: 4 }}>
              The Learner extracts lessons from every turn and writes them to <code style={{ background: "var(--surface-deep)", padding: "2px 6px", borderRadius: 4 }}>.shellack/thread-memory/</code> and <code style={{ background: "var(--surface-deep)", padding: "2px 6px", borderRadius: 4 }}>.shellack/persona-tuning.md</code>. The Historian reads from these same sources when checking for prior decisions. This closes the learning loop: a mistake made in Thread A becomes a lesson that Historian surfaces in Thread B. Without this connection, the Learner writes into a void — lessons extracted but never consulted.
            </div>
          </div>

          {/* Vision group explanation */}
          <div style={{ marginTop: 12, background: "var(--surface)", border: "1px solid #c084fc", borderRadius: 10, padding: 16 }}>
            <div style={{ fontWeight: 700, fontSize: 14, color: "#c084fc", marginBottom: 8, fontFamily: "var(--font-mono)" }}>New Parallel Group: B+ (Vision & Measurement)</div>
            <div style={{ fontSize: 12, color: "var(--text-secondary)", lineHeight: 1.6 }}>
              Dreamer + Insights + Growth Coach fire together after Group B (Design) and before Group C (Challenge). This means they see the formed proposal and can add vision/measurement context before the challenge phase tears it apart. The Skeptic benefits from knowing "this has measurable success criteria" — it changes what's worth challenging.
            </div>
            <div style={{ marginTop: 10, display: "flex", gap: 6 }}>
              {["A: Plan", "B: Design", "B+: Vision", "C: Challenge", "D: Security", "E: Quality", "F: Synthesis"].map((g, i) => (
                <span key={g} style={{
                  fontSize: 10, padding: "3px 8px", borderRadius: 6,
                  background: i === 2 ? "#c084fc18" : "var(--surface-deep)",
                  color: i === 2 ? "#c084fc" : "var(--text-tertiary)",
                  fontWeight: i === 2 ? 700 : 500,
                  fontFamily: "var(--font-mono)",
                  border: i === 2 ? "1px solid #c084fc40" : "1px solid transparent",
                }}>{g}</span>
              ))}
            </div>
          </div>
        </div>
      )}

      {view === "roster" && (
        <div>
          <div style={{ fontSize: 12, color: "var(--text-secondary)", lineHeight: 1.6, marginBottom: 16 }}>
            Full roster: 25 cognitive personas + 4 infrastructure agents. Sorted by execution order within the turn.
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))", gap: 6 }}>
            {[
              ...PHASES.flatMap(p => p.agents.map(a => ({ ...a, phase: p.label, phaseColor: p.color }))),
            ].map((a, i) => (
              <div key={`${a.name}-${i}`} style={{
                background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 8,
                padding: "10px 12px", display: "flex", alignItems: "center", gap: 8,
              }}>
                <span style={{ fontSize: 18 }}>{a.emoji}</span>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontWeight: 700, fontSize: 12, color: "var(--text-primary)", fontFamily: "var(--font-mono)" }}>{a.name}</div>
                  <div style={{ fontSize: 10, color: "var(--text-secondary)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{a.action}</div>
                </div>
                <span style={{ fontSize: 9, padding: "2px 6px", borderRadius: 99, background: `${a.phaseColor}18`, color: a.phaseColor, fontWeight: 600, fontFamily: "var(--font-mono)", whiteSpace: "nowrap", flexShrink: 0 }}>{a.phase}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
