import type { ExecutedClick } from "../generation-types";
import { clickMarkerPosition } from "./vision-click-model";

export function VisionClickOverlay({ click, image, container, pulse }: {
  click: ExecutedClick; image: { width: number; height: number }; container: { width: number; height: number }; pulse: boolean;
}) {
  const position = clickMarkerPosition(click, image, container);
  return position && <span aria-hidden="true" data-testid="vision-click-marker" className={"vision-click-marker" + (pulse ? " vision-click-marker--pulse" : "")} style={position} />;
}
