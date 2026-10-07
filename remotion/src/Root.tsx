import type {ComponentType} from "react";
import {Composition} from "remotion";

import demoStory from "../data/visual-story.demo.json";
import {AttributionEvidenceStory} from "./AttributionEvidenceStory";
import type {VisualStory} from "./types";

export function RemotionRoot() {
  const component = AttributionEvidenceStory as unknown as ComponentType<Record<string, unknown>>;
  const defaultProps = demoStory as unknown as Record<string, unknown>;

  return (
    <Composition
      id="AttributionEvidenceStory"
      component={component}
      durationInFrames={1350}
      fps={30}
      width={1920}
      height={1080}
      defaultProps={defaultProps as VisualStory}
    />
  );
}
