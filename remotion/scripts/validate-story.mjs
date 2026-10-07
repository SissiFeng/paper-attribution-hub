import {readAndValidateStory} from "./story-validation.mjs";

const file = process.argv[2] ?? "data/visual-story.demo.json";
const {story, resolved} = readAndValidateStory(file);

console.log(
  `valid ${story.contract_version}: ${story.story_id} (${story.data_status}) from ${resolved}`,
);

