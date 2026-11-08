import { SectionHeading } from "./common";
import { FlavorWheelView } from "./FlavorWheelView";
import { GlossaryView } from "./GlossaryView";
import { DesignatedBrandsView } from "./DesignatedBrandsView";
import { VarietyGuideView } from "./VarietyGuideView";
import { BrewGuideView } from "./BrewGuideView";
import { EventsView, CompetitionsView } from "./EventsView";

// 「豆知識」画面。どのサブ画面を開くか(subTab)は、下部メニューの子メニューから
// 選ばれて親(App.jsx)から渡される。
export function TriviaView({ subTab, onLearnOrigin, events }) {
  return (
    <div className="max-w-xl mx-auto">
      <div className="px-5 pt-4">
        <SectionHeading en="Trivia" ja="豆知識" />
      </div>

      {subTab === "flavorWheel" && <FlavorWheelView />}
      {subTab === "glossary" && <GlossaryView />}
      {subTab === "brands" && <DesignatedBrandsView onLearnOrigin={onLearnOrigin} />}
      {subTab === "variety" && <VarietyGuideView />}
      {subTab === "brew" && <BrewGuideView />}
      {subTab === "events" && <EventsView onLearnOrigin={onLearnOrigin} events={events} />}
      {subTab === "competitions" && <CompetitionsView events={events} />}
    </div>
  );
}
