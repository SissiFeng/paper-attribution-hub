import {interpolate, useCurrentFrame} from "remotion";

import type {VisualStory} from "./types";
import {FlowMap} from "./components/FlowMap";
import {
  Background,
  displayFont,
  Kicker,
  monoFont,
  palette,
  reveal,
  Scene,
  StoryFooter,
} from "./components/SceneFrame";
import {TimelineChart} from "./components/TimelineChart";

const INTRO = {start: 0, duration: 180};
const TIMELINE = {start: 180, duration: 300};
const FLOW = {start: 480, duration: 300};
const EVIDENCE = {start: 780, duration: 330};
const AUDIT = {start: 1110, duration: 240};

const toneColor = {
  gold: palette.gold,
  teal: palette.teal,
  rose: palette.rose,
};

export function AttributionEvidenceStory(story: VisualStory) {
  const frame = useCurrentFrame();
  const introFrame = frame - INTRO.start;
  const timelineFrame = frame - TIMELINE.start;
  const flowFrame = frame - FLOW.start;
  const evidenceFrame = frame - EVIDENCE.start;
  const auditFrame = frame - AUDIT.start;

  return (
    <div style={{width: "100%", height: "100%", color: palette.paper}}>
      <Background />

      <Scene {...INTRO}>
        <div style={{display: "grid", gridTemplateColumns: "1.18fr .82fr", gap: 110, alignItems: "center", height: "100%"}}>
          <div>
            <div style={{opacity: reveal(introFrame, 12), transform: `translateY(${(1 - reveal(introFrame, 12)) * 20}px)`}}>
              <Kicker>Paper Attribution System / evidence story</Kicker>
            </div>
            <h1
              style={{
                fontFamily: displayFont,
                fontSize: 122,
                lineHeight: 0.9,
                letterSpacing: "-0.045em",
                fontWeight: 520,
                margin: "42px 0 32px",
                maxWidth: 960,
                opacity: reveal(introFrame, 28, 28),
                transform: `translateY(${(1 - reveal(introFrame, 28, 28)) * 34}px)`,
              }}
            >
              Attribution,
              <br />
              <em style={{color: palette.gold, fontWeight: 430}}>made inspectable.</em>
            </h1>
            <p
              style={{
                fontFamily: monoFont,
                fontSize: 22,
                lineHeight: 1.6,
                color: palette.muted,
                maxWidth: 790,
                opacity: reveal(introFrame, 52),
              }}
            >
              {story.subtitle}
            </p>
          </div>
          <div
            style={{
              opacity: reveal(introFrame, 48, 30),
              transform: `translateX(${(1 - reveal(introFrame, 48, 30)) * 32}px)`,
              border: `1px solid ${palette.line}`,
              borderRadius: 34,
              padding: "38px 42px",
              background: "rgba(13,26,32,.76)",
              boxShadow: "0 34px 90px rgba(0,0,0,.3)",
            }}
          >
            <Kicker color={palette.teal}>Frozen scope</Kicker>
            <div style={{fontFamily: displayFont, fontSize: 98, lineHeight: 1, marginTop: 34}}>{story.scope.included_papers}</div>
            <div style={{fontFamily: monoFont, fontSize: 18, color: palette.muted, marginTop: 10}}>ILLUSTRATIVE DISTINCT PAPERS</div>
            <div style={{height: 1, background: palette.line, margin: "34px 0"}} />
            <div style={{fontFamily: monoFont, fontSize: 16, lineHeight: 1.75, color: palette.paper}}>{story.scope.label}</div>
            <div style={{fontFamily: monoFont, fontSize: 14, lineHeight: 1.65, color: palette.muted, marginTop: 18}}>{story.period_label}</div>
          </div>
        </div>
      </Scene>

      <Scene {...TIMELINE}>
        <Kicker>01 / temporal signal</Kicker>
        <div style={{display: "flex", justifyContent: "space-between", alignItems: "end", marginTop: 20}}>
          <h2 style={{fontFamily: displayFont, fontSize: 72, fontWeight: 480, letterSpacing: "-.03em", margin: 0}}>
            Evidence accumulates in time.
          </h2>
          <div style={{fontFamily: monoFont, color: palette.muted, fontSize: 15}}>DESCRIPTIVE REPLAY · NOT CAUSAL PROOF</div>
        </div>
        <TimelineChart story={story} frame={timelineFrame} />
        <p style={{fontFamily: monoFont, color: palette.muted, fontSize: 15, marginTop: 18}}>{story.timeline.annotation}</p>
      </Scene>

      <Scene {...FLOW}>
        <Kicker color={palette.teal}>02 / relationship flow</Kicker>
        <div style={{display: "flex", justifyContent: "space-between", alignItems: "end", marginTop: 20}}>
          <h2 style={{fontFamily: displayFont, fontSize: 72, fontWeight: 480, letterSpacing: "-.03em", margin: 0}}>
            Every ribbon keeps its meaning.
          </h2>
          <div style={{fontFamily: monoFont, color: palette.muted, fontSize: 15}}>INSTITUTION → TOPIC → LABEL</div>
        </div>
        <FlowMap story={story} frame={flowFrame} />
        <p style={{fontFamily: monoFont, color: palette.muted, fontSize: 15, marginTop: 16}}>{story.flow.annotation}</p>
      </Scene>

      <Scene {...EVIDENCE}>
        <Kicker color={palette.rose}>03 / evidence before narrative</Kicker>
        <h2 style={{fontFamily: displayFont, fontSize: 76, fontWeight: 480, letterSpacing: "-.03em", margin: "22px 0 48px"}}>
          The claim travels with its trace.
        </h2>
        <div style={{display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 28}}>
          {story.evidence_cards.map((card, index) => {
            const cardReveal = reveal(evidenceFrame, 34 + index * 28, 26);
            const color = toneColor[card.tone];
            return (
              <article
                key={card.eyebrow}
                style={{
                  opacity: cardReveal,
                  transform: `translateY(${(1 - cardReveal) * 38}px)`,
                  minHeight: 460,
                  border: `1px solid ${palette.line}`,
                  borderRadius: 30,
                  background: "rgba(13,26,32,.78)",
                  padding: "34px 34px 30px",
                  display: "flex",
                  flexDirection: "column",
                  boxShadow: "0 34px 74px rgba(0,0,0,.22)",
                }}
              >
                <div style={{fontFamily: monoFont, fontSize: 15, color, textTransform: "uppercase", letterSpacing: ".14em"}}>{card.eyebrow}</div>
                <div style={{fontFamily: displayFont, fontSize: 116, lineHeight: 1, color, marginTop: 44}}>{card.value}</div>
                <div style={{fontFamily: monoFont, fontSize: 18, color: palette.paper, textTransform: "uppercase", letterSpacing: ".08em", marginTop: 10}}>{card.label}</div>
                <p style={{fontFamily: monoFont, color: palette.muted, fontSize: 17, lineHeight: 1.65, marginTop: 36}}>{card.detail}</p>
                <div style={{marginTop: "auto", paddingTop: 28, borderTop: `1px solid ${palette.line}`, fontFamily: monoFont, color, fontSize: 13, lineHeight: 1.45, wordBreak: "break-all"}}>
                  SOURCE {card.source_link}
                </div>
              </article>
            );
          })}
        </div>
      </Scene>

      <Scene {...AUDIT}>
        <div style={{display: "grid", gridTemplateColumns: "1.05fr .95fr", gap: 92, alignItems: "center", height: "100%"}}>
          <div>
            <Kicker>04 / reproducible by construction</Kicker>
            <h2
              style={{
                fontFamily: displayFont,
                fontSize: 88,
                lineHeight: 0.98,
                fontWeight: 480,
                letterSpacing: "-.035em",
                margin: "34px 0 40px",
                opacity: reveal(auditFrame, 18),
              }}
            >
              A moving picture,
              <br />
              <em style={{color: palette.gold}}>with a stationary record.</em>
            </h2>
            <p style={{fontFamily: monoFont, fontSize: 18, color: palette.muted, lineHeight: 1.7, maxWidth: 760}}>
              The video is an interpretation layer. The frozen JSON, metric definitions, source links, and hashes remain the source of truth.
            </p>
          </div>
          <div
            style={{
              opacity: reveal(auditFrame, 38, 28),
              transform: `translateY(${(1 - reveal(auditFrame, 38, 28)) * 24}px)`,
              border: `1px solid ${palette.line}`,
              borderRadius: 30,
              padding: "34px 38px",
              background: "rgba(13,26,32,.8)",
            }}
          >
            {[
              ["CONTRACT", story.contract_version],
              ["ALGORITHM", story.audit.algorithm],
              ["FILTER", story.audit.filter_fingerprint],
              ["PAPER SET", story.audit.paper_set_sha256],
              ["GENERATED", story.generated_at],
            ].map(([label, value], index) => (
              <div key={label} style={{padding: index === 0 ? "0 0 22px" : "22px 0", borderTop: index === 0 ? undefined : `1px solid ${palette.line}`}}>
                <div style={{fontFamily: monoFont, fontSize: 12, color: palette.muted, letterSpacing: ".14em"}}>{label}</div>
                <div style={{fontFamily: monoFont, fontSize: 15, color: index >= 2 ? palette.teal : palette.paper, marginTop: 9, lineHeight: 1.5, wordBreak: "break-all"}}>
                  {index >= 2 && value.length > 34 ? `${value.slice(0, 34)}…` : value}
                </div>
              </div>
            ))}
          </div>
        </div>
      </Scene>

      <StoryFooter story={story} />
      <div
        style={{
          position: "absolute",
          left: 0,
          bottom: 0,
          height: 4,
          width: `${interpolate(frame, [0, 1349], [0, 100], {extrapolateRight: "clamp"})}%`,
          background: `linear-gradient(90deg, ${palette.teal}, ${palette.gold})`,
        }}
      />
    </div>
  );
}

