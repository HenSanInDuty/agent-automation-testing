import type { ExecutedClick, VisualLocator } from "../generation-types";
import { clickMarkerPosition, clickTargetPosition } from "./vision-click-model";

export function VisionClickOverlay({ click, image, container, pulse, target }: {
  click: ExecutedClick; image: { width: number; height: number }; container: { width: number; height: number }; pulse: boolean;
  target?: VisualLocator["bounding_box"];
}) {
  const position = clickMarkerPosition(click, image, container);
  const bounds = target && clickTargetPosition(click, target, image, container);
  return position && <>
    {bounds && <span aria-hidden="true" data-testid="vision-click-target" className="vision-click-target" style={bounds} />}
    <span aria-hidden="true" data-testid="vision-click-marker" className={"vision-click-marker" + (pulse ? " vision-click-marker--pulse" : "")} style={position} />
  </>;
}
