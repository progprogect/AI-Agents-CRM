/** Registry of custom React Flow node types. */
import { StepNode } from "./StepNode";
import { StartNode } from "./StartNode";

export const nodeTypes = {
  stepNode: StepNode,
  startNode: StartNode,
} as const;
