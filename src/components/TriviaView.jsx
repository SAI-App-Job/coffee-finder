import { useState } from "react";
import { SectionHeading } from "./common";
import { FlavorWheelView } from "./FlavorWheelView";
import { GlossaryView } from "./GlossaryView";
import { DesignatedBrandsView } from "./DesignatedBrandsView";
import { VarietyGuideView } from "./VarietyGuideView";
import { BrewGuideView } from "./BrewGuideView";
import { EventsView } from "./EventsView";
import { TRIVIA_SUB_TABS } from "../data/navigation";

export function TriviaView({ onLearnOrigin, events }) {
  const [subTab, setSubTab] = useState("flavorWheel");

  return (
    <div className="max-w-xl mx-auto">
      <div className="px-5 pt-4">
        <SectionHeading en="Trivia" ja="豆知識" />
        <div className="grid grid-cols-3 gap-1.5 mt-4">
          {TRIVIA_SUB_TABS.map(({ id, icon: Icon, ja }) => (
            <button
              key={id}
              onClick={() => setSubTab(id)}
              className={`flex flex-col items-center justify-center gap-1 py-2.5 px-1 rounded-xl transition-colors ${
                subTab === id ? "bg-[var(--accent)] text-[#231810]" : "bg-[#3B2211] text-[#B8A891]"
              }`}
            >
              <Icon size={16} strokeWidth={2} />
              <span className="text-[11px] font-medium leading-tight text-center">{ja}</span>
            </button>
          ))}
        </div>
      </div>

      {subTab === "flavorWheel" && <FlavorWheelView />}
      {subTab === "glossary" && <GlossaryView />}
      {subTab === "brands" && <DesignatedBrandsView onLearnOrigin={onLearnOrigin} />}
      {subTab === "variety" && <VarietyGuideView />}
      {subTab === "brew" && <BrewGuideView />}
      {subTab === "events" && <EventsView onLearnOrigin={onLearnOrigin} events={events} />}
    </div>
  );
}
