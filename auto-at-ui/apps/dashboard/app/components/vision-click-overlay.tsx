import type { ExecutedClick, VisualLocator } from "../generation-types";
import { clickMarkerPosition, clickTargetPosition } from "./vision-click-model";

// The marker is drawn on top of arbitrary screenshots, so it keeps fixed high-contrast colours instead of theme tokens.
export const clickTargetClass = "pointer-events-none absolute rounded-[4px] border-2 border-[#facc15] bg-[rgb(250_204_21/0.18)] shadow-[0_0_0_1px_#172033,0_0_0_3px_rgb(255_255_255/0.8)]";

export function VisionClickOverlay({ click, image, container, pulse, target }: {
  click: ExecutedClick; image: { width: number; height: number }; container: { width: number; height: number }; pulse: boolean;
  target?: VisualLocator["bounding_box"];
}) {
  const position = clickMarkerPosition(click, image, container);
  const bounds = target && clickTargetPosition(click, target, image, container);
  return position && <>
    {bounds && <span aria-hidden="true" data-testid="vision-click-target" className={clickTargetClass} style={bounds} />}
    <span aria-hidden="true" data-testid="vision-click-marker" className={"pointer-events-none absolute z-[1] size-8 -translate-x-1/2 -translate-y-1/2 rounded-full border-[3px] border-[#facc15] bg-[rgb(250_204_21/0.15)] shadow-[0_0_0_2px_#172033,0_0_0_4px_rgb(255_255_255/0.9)] after:absolute after:top-1/2 after:left-1/2 after:size-[5px] after:-translate-x-1/2 after:-translate-y-1/2 after:rounded-full after:bg-[#172033] after:content-['']" + (pulse ? " animate-[vision-click-pulse_0.6s_ease-out_2] motion-reduce:animate-none" : "")} style={position} />
  </>;
}
