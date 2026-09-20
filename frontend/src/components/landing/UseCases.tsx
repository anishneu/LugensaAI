import { Tab, TabGroup, TabList, TabPanel, TabPanels } from "@headlessui/react";
import { ArrowRightIcon, BuildingStorefrontIcon, HomeModernIcon, PaperAirplaneIcon } from "@heroicons/react/24/outline";

interface UseCase {
  id: string;
  label: string;
  Icon: typeof PaperAirplaneIcon;
  title: string;
  body: string;
  questions: string[];
  looksAt: string[];
}

// The topics are the ones the planner really has (backend/app/planning/topics.py); a question picks the few that matter.
const USE_CASES: UseCase[] = [
  {
    id: "trip",
    label: "Planning a trip",
    Icon: PaperAirplaneIcon,
    title: "Know a place before you land",
    body: "Ask what a neighborhood is like to visit, and it reads what visitors and locals actually say, in the local language, then tells you where the sources agree and where they don't.",
    questions: ["Is it a good place to visit as a tourist?", "Is it safe, and easy to get around?", "What's the food like, and what do people say about the crowds?"],
    looksAt: ["Attractions", "Climate", "Customs", "Getting around", "Safety", "Food"],
  },
  {
    id: "move",
    label: "Moving somewhere",
    Icon: HomeModernIcon,
    title: "Live there in your head first",
    body: "For a move, the questions are different: rent, commute, safety after dark, healthcare. Each is researched on its own and answered only from what the sources support.",
    questions: ["Would this be a good place to live?", "What's the neighborhood like at night?", "How is public transport, and what does a typical week cost?"],
    looksAt: ["Housing", "Transport", "Safety", "Cost of living", "Healthcare", "Community"],
  },
  {
    id: "business",
    label: "Checking a business",
    Icon: BuildingStorefrontIcon,
    title: "Reviews from everywhere, side by side",
    body: "For a specific restaurant, hotel or venue it brings Google Maps ratings and reviews together with TripAdvisor, Reddit and local forums, and lists what people disagree on.",
    questions: ["How are the reviews of this restaurant?", "Is it worth the price?", "What do people complain about?"],
    looksAt: ["Google Maps rating", "Recent reviews", "Forums", "Price", "Hours", "What's nearby"],
  },
];

export function UseCases({ onTry }: { onTry: (question: string) => void }) {
  return (
    <TabGroup>
      <TabList className="mx-auto mb-10 flex w-fit max-w-full gap-1 overflow-x-auto rounded-full border border-white/12 bg-white/[0.04] p-1.5">
        {USE_CASES.map(({ id, label, Icon }) => (
          <Tab
            key={id}
            className="flex flex-shrink-0 items-center gap-2 rounded-full px-4 py-2 text-sm font-semibold whitespace-nowrap text-white/60 outline-none transition-colors data-[hover]:text-white data-[selected]:bg-white data-[selected]:text-[#0b0a14] data-[focus]:ring-2 data-[focus]:ring-violet-400"
          >
            <Icon className="h-4.5 w-4.5" aria-hidden="true" />
            {label}
          </Tab>
        ))}
      </TabList>

      <TabPanels>
        {USE_CASES.map((useCase) => (
          <TabPanel key={useCase.id} className="grid items-stretch gap-6 outline-none md:grid-cols-2">
            <div className="flex flex-col gap-5 rounded-2xl border border-white/10 bg-white/[0.03] p-7">
              <h3 className="m-0 text-2xl font-semibold tracking-tight text-white">{useCase.title}</h3>
              <p className="m-0 text-[15px] leading-relaxed text-white/65">{useCase.body}</p>
              <p className="m-0 mt-1 text-[11px] font-semibold tracking-[0.14em] text-violet-300 uppercase">It looks at</p>
              <ul className="m-0 flex list-none flex-wrap gap-2 p-0">
                {useCase.looksAt.map((topic) => (
                  <li key={topic} className="rounded-full border border-white/12 bg-white/[0.05] px-3 py-1 text-xs text-white/75">
                    {topic}
                  </li>
                ))}
              </ul>
            </div>

            <div className="flex flex-col gap-3 rounded-2xl border border-white/10 bg-gradient-to-br from-violet-500/[0.13] to-transparent p-7">
              <p className="m-0 text-[11px] font-semibold tracking-[0.14em] text-violet-300 uppercase">Questions to start with</p>
              {useCase.questions.map((question) => (
                <button
                  key={question}
                  type="button"
                  onClick={() => onTry(question)}
                  className="group flex items-center justify-between gap-4 rounded-xl border border-white/10 bg-[#0d0b1a]/70 px-4 py-3.5 text-left text-[15px] text-white/90 transition hover:border-violet-400/60 hover:bg-[#0d0b1a]"
                >
                  {question}
                  <ArrowRightIcon className="h-4 w-4 flex-shrink-0 text-white/40 transition group-hover:translate-x-0.5 group-hover:text-violet-300" aria-hidden="true" />
                </button>
              ))}
              <p className="m-0 mt-auto pt-2 text-xs leading-relaxed text-white/40">You pick the place first; the question is then asked about it.</p>
            </div>
          </TabPanel>
        ))}
      </TabPanels>
    </TabGroup>
  );
}
