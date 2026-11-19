import React from "react";
import { Composition } from "remotion";
import { Card, CardProps } from "./Card";

const FPS = 30;

const defaults: CardProps = {
  kind: "stat",
  fmt: "short",
  duration: 3,
  palette: ["#0c0a09", "#3b0764", "#c084fc"],
  value: "8,000 feet",
  label: "altitude",
};

export const Root: React.FC = () => (
  <Composition
    id="Card"
    component={Card}
    fps={FPS}
    width={1080}
    height={1920}
    durationInFrames={90}
    defaultProps={defaults}
    calculateMetadata={({ props }) => {
      const long = props.fmt === "long";
      return {
        durationInFrames: Math.max(15, Math.round(props.duration * FPS)),
        width: long ? 1920 : 1080,
        height: long ? 1080 : 1920,
      };
    }}
  />
);
