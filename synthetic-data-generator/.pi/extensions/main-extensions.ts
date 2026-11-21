import { mkdir, readFile, writeFile } from "node:fs/promises";
import { join } from "node:path";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { Type } from "typebox";

const categories = [
  "work",
  "travel",
  "school",
  "shopping",
  "family interactions",
  "daily planning",
] as const;

const parameterNames = {
  work: "work",
  travel: "travel",
  school: "school",
  shopping: "shopping",
  "family interactions": "family_interactions",
  "daily planning": "daily_planning",
} as const;

function isUserRecord(value: unknown): value is Record<string, unknown> {
  return (
    typeof value === "object" &&
    value !== null &&
    !Array.isArray(value) &&
    "user_id" in value &&
    typeof value.user_id === "string"
  );
}

export default function (pi: ExtensionAPI) {
  pi.registerTool({
    name: "populate_conversation_starters",
    label: "Populate conversation starters",
    description:
      "Add questions to a user's conversation-starter categories in the JSON data file.",
    parameters: Type.Object({
      user_id: Type.String({ description: "ID of the user" }),
      work: Type.Optional(
        Type.Array(Type.String(), {
          description: "Questions or conversation starters about work.",
        }),
      ),
      travel: Type.Optional(
        Type.Array(Type.String(), {
          description: "Questions or conversation starters about travel.",
        }),
      ),
      school: Type.Optional(
        Type.Array(Type.String(), {
          description: "Questions or conversation starters about school.",
        }),
      ),
      shopping: Type.Optional(
        Type.Array(Type.String(), {
          description: "Questions or conversation starters about shopping.",
        }),
      ),
      family_interactions: Type.Optional(
        Type.Array(Type.String(), {
          description:
            "Questions or conversation starters about family interactions.",
        }),
      ),
      daily_planning: Type.Optional(
        Type.Array(Type.String(), {
          description: "Questions or conversation starters about daily planning.",
        }),
      ),
    }),
    async execute(_toolCallId, params) {
      const dataDirectory = join(process.cwd(), "data");
      const filePath = join(
        dataDirectory,
        "synthetic_conversation_starter.json",
      );
      await mkdir(dataDirectory, { recursive: true });

      let parsed: unknown;
      try {
        parsed = JSON.parse(await readFile(filePath, "utf8"));
      } catch (error) {
        if (
          !(error instanceof Error) ||
          !("code" in error) ||
          error.code !== "ENOENT"
        ) {
          throw error;
        }
        parsed = [];
      }

      if (!Array.isArray(parsed) || !parsed.every(isUserRecord)) {
        throw new Error(
          `${filePath} must contain a JSON array of user records.`,
        );
      }

      const records = parsed;
      let record = records.find((item) => item.user_id === params.user_id);
      if (!record) {
        record = { user_id: params.user_id };
        for (const category of categories) {
          record[category] = [];
        }
        records.push(record);
      }

      for (const category of categories) {
        const questions = params[parameterNames[category]];
        const existing = record[category] ?? [];
        if (
          !Array.isArray(existing) ||
          !existing.every((item) => typeof item === "string")
        ) {
          throw new Error(
            `The "${category}" field for user ${params.user_id} must be a string array.`,
          );
        }
        record[category] = questions ? [...existing, ...questions] : existing;
      }

      await writeFile(
        filePath,
        `${JSON.stringify(records, null, 2)}\n`,
        "utf8",
      );

      return {
        content: [
          {
            type: "text",
            text: `Added conversation-starter questions for user ${params.user_id}.`,
          },
        ],
        details: {},
      };
    },
  });
}
