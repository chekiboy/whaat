import { type ReactNode, useEffect, useRef } from "react";
import { DetailShell, Grip, useDetailWidth } from "@/components/memory/memory-split";

/** A drawing (an embedded frame) under the view's toolbar, its details opening on a click beside it: by default the
    drawing keeps 65% and the details take 35%, dragged on the grip and remembered apart from the
    list's width. The frame stays the first child, so opening the details never reloads it. */
export function DrawingSplit({
  toolbar,
  frame,
  detail,
  onClose,
}: {
  toolbar: ReactNode;
  frame: ReactNode;
  detail: ReactNode | null;
  onClose: () => void;
}) {
  const host = useRef<HTMLDivElement>(null);
  const {
    dragging,
    startDrag,
    resetWidth,
    detail: width,
  } = useDetailWidth(host, {
    key: "whaat-drawing-detail-width",
    share: 35,
  });
  const open = detail != null;
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !["INPUT", "TEXTAREA"].includes((e.target as HTMLElement).tagName)) onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  return (
    <div
      ref={host}
      className={`mem-split${open ? " open" : ""}${dragging ? " dragging" : ""}`}
      style={{ "--dw": open ? width : "0px" } as React.CSSProperties}
    >
      <div className="dv-pane">
        {toolbar}
        <div className="dv-stage">{frame}</div>
      </div>
      {open && (
        <>
          <Grip onPointerDown={startDrag} onDoubleClick={resetWidth} />
          <DetailShell onClose={onClose}>{detail}</DetailShell>
        </>
      )}
    </div>
  );
}
