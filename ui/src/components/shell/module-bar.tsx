import { createContext, type ReactNode, useContext, useState } from "react";
import { createPortal } from "react-dom";

const SlotContext = createContext<{ slot: HTMLElement | null; setSlot: (el: HTMLElement | null) => void }>({
  slot: null,
  setSlot: () => {},
});

export function ModuleBarProvider({ children }: { children: ReactNode }) {
  const [slot, setSlot] = useState<HTMLElement | null>(null);
  return <SlotContext value={{ slot, setSlot }}>{children}</SlotContext>;
}

/** Where a page's own navigation goes: the module bar beside the rail. */
export function ModuleBarSlot() {
  const { setSlot } = useContext(SlotContext);
  return <div className="sh-mod-body" ref={setSlot} />;
}

/** A page puts its views, filters or sections into the module bar with this. */
export function ModuleBar({ children }: { children: ReactNode }) {
  const { slot } = useContext(SlotContext);
  return slot ? createPortal(children, slot) : null;
}

export function ModuleBarSection({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="sh-sec">
      <h3>{title}</h3>
      {children}
    </section>
  );
}
