/** Registry of custom React Flow node types. */
import { StepNode } from "./StepNode";
import { StartNode } from "./StartNode";
import { AutoStepNode } from "./AutoStepNode";

export const nodeTypes = {
  stepNode: StepNode,
  startNode: StartNode,
  autoStepNode: AutoStepNode,
} as const;
