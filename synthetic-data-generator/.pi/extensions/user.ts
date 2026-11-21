import { randomUUID } from "node:crypto";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { Type } from "typebox";

const dataDirectory = join(process.cwd(), "data");
const profilesPath = join(dataDirectory, "user_profiles.json");
const activitiesPath = join(dataDirectory, "user_activities.json");

const themeSchema = Type.Union(
  [
    Type.Literal("work"),
    Type.Literal("travel"),
    Type.Literal("school"),
    Type.Literal("shopping"),
    Type.Literal("family"),
    Type.Literal("daily_planning"),
  ],
  {
    description:
      "Theme: work, travel, school, shopping, family, or daily_planning.",
  },
);

const activityTypeSchema = Type.Union(
  [
    Type.Literal("booking"),
    Type.Literal("appointment"),
    Type.Literal("task"),
    Type.Literal("reminder"),
    Type.Literal("shopping_item"),
  ],
  {
    description:
      "Activity type: booking, appointment, task, reminder, or shopping_item.",
  },
);

type StoredRecord = Record<string, unknown>;

function isStoredRecord(value: unknown): value is StoredRecord {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

async function readRecords(path: string): Promise<StoredRecord[]> {
  let contents: string;
  try {
    contents = await readFile(path, "utf8");
  } catch (error) {
    if (
      error instanceof Error &&
      "code" in error &&
      error.code === "ENOENT"
    ) {
      return [];
    }
    throw error;
  }

  const parsed: unknown = JSON.parse(contents);
  if (!Array.isArray(parsed) || !parsed.every(isStoredRecord)) {
    throw new Error(`${path} must contain a JSON array of records.`);
  }
  return parsed;
}

async function writeRecords(path: string, records: StoredRecord[]) {
  await mkdir(dirname(path), { recursive: true });
  await writeFile(path, `${JSON.stringify(records, null, 2)}\n`, "utf8");
}

function requireText(value: string, label: string): string {
  if (!value.trim()) throw new Error(`${label} must not be empty.`);
  return value;
}

function formatInput(record: StoredRecord): string {
  return JSON.stringify(record, null, 2);
}

function textResult(text: string) {
  return { content: [{ type: "text" as const, text }], details: {} };
}

export default function (pi: ExtensionAPI) {
  pi.registerTool({
    name: "save_user_profile",
    label: "Save user profile",
    description:
      "Save or update a user's basic contact profile locally. Always confirm the displayed information before it is written.",
    parameters: Type.Object({
      profile_id: Type.String({ description: "ID of the synthetic user profile" }),
      first_name: Type.String({ description: "User's first name" }),
      last_name: Type.String({ description: "User's last name" }),
      mobile_phone: Type.String({ description: "User's mobile phone number" }),
      email: Type.Optional(Type.String({ description: "User's email address" })),
      country: Type.Optional(Type.String({ description: "User's country" })),
      preferred_language: Type.Optional(
        Type.String({ description: "User's preferred language" }),
      ),
    }),
    async execute(_toolCallId, params, _signal, _onUpdate, ctx) {
      const profileId = requireText(params.profile_id, "Profile ID");
      const profiles = await readRecords(profilesPath);
      const existingIndex = profiles.findIndex(
        (profile) => profile.profile_id === profileId,
      );
      const previous: StoredRecord =
        existingIndex >= 0 ? profiles[existingIndex] : {};
      const profile: StoredRecord = {
        ...previous,
        profile_id: profileId,
        first_name: requireText(params.first_name, "First name"),
        last_name: requireText(params.last_name, "Last name"),
        mobile_phone: requireText(params.mobile_phone, "Mobile phone"),
      };

      for (const field of ["email", "country", "preferred_language"] as const) {
        const value = params[field];
        if (value !== undefined) profile[field] = requireText(value, field);
      }

      const summary = formatInput(profile);
      const confirmed = await ctx.ui.confirm(
        "Confirm user profile",
        `Review these exact details before saving or updating the local profile:\n${summary}`,
      );
      if (!confirmed) {
        return textResult(`Canceled. No profile was saved.\n${summary}`);
      }

      if (existingIndex >= 0) profiles[existingIndex] = profile;
      else profiles.push(profile);
      await writeRecords(profilesPath, profiles);
      return textResult(`Profile saved. Confirmed input:\n${summary}`);
    },
  });

  pi.registerTool({
    name: "get_user_profile",
    label: "Get user profile",
    description: "Read a previously saved local profile by profile ID.",
    parameters: Type.Object({
      profile_id: Type.String({
        description: "ID of the user profile to retrieve",
      }),
    }),
    async execute(_toolCallId, params) {
      const profileId = requireText(params.profile_id, "Profile ID");
      const profiles = await readRecords(profilesPath);
      const profile = profiles.find((item) => item.profile_id === profileId);
      if (!profile) return textResult(`No saved profile found for ${profileId}.`);
      return textResult(
        `Profile retrieved for profile_id ${profileId}:\n${formatInput(profile)}`,
      );
    },
  });

  pi.registerTool({
    name: "record_user_activity",
    label: "Record user activity",
    description:
      "Save a themed task, appointment, booking, reminder, or shopping item locally. Confirm all submitted details before saving.",
    parameters: Type.Object({
      profile_id: Type.String({ description: "ID of the synthetic user profile" }),
      theme: themeSchema,
      activity_type: activityTypeSchema,
      title: Type.String({ description: "Short name or purpose of the activity" }),
      date_time: Type.Optional(
        Type.String({ description: "Activity date/time, if provided" }),
      ),
      location: Type.Optional(
        Type.String({ description: "Activity location, if provided" }),
      ),
      contact_name: Type.Optional(
        Type.String({ description: "Relevant person's name, if provided" }),
      ),
      mobile_phone: Type.Optional(
        Type.String({ description: "Relevant mobile number, if provided" }),
      ),
      notes: Type.Optional(
        Type.String({ description: "Additional user-provided details" }),
      ),
    }),
    async execute(_toolCallId, params, _signal, _onUpdate, ctx) {
      const submittedInput: StoredRecord = {
        profile_id: requireText(params.profile_id, "Profile ID"),
        theme: params.theme,
        activity_type: params.activity_type,
        title: requireText(params.title, "Title"),
      };
      for (const field of [
        "date_time",
        "location",
        "contact_name",
        "mobile_phone",
        "notes",
      ] as const) {
        const value = params[field];
        if (value !== undefined) {
          submittedInput[field] = requireText(value, field);
        }
      }

      const summary = formatInput(submittedInput);
      const confirmed = await ctx.ui.confirm(
        "Confirm user activity",
        `Review these exact details before saving the activity:\n${summary}`,
      );
      if (!confirmed) {
        return textResult(`Canceled. No activity was saved.\n${summary}`);
      }

      const activities = await readRecords(activitiesPath);
      activities.push({
        ...submittedInput,
        activity_id: randomUUID(),
        created_at: new Date().toISOString(),
      });
      await writeRecords(activitiesPath, activities);
      return textResult(`Activity saved. Confirmed input:\n${summary}`);
    },
  });

  pi.registerTool({
    name: "list_user_activities",
    label: "List user activities",
    description:
      "List saved local activities for a profile, optionally filtered by theme.",
    parameters: Type.Object({
      profile_id: Type.String({ description: "ID of the user profile" }),
      theme: Type.Optional(themeSchema),
    }),
    async execute(_toolCallId, params) {
      const profileId = requireText(params.profile_id, "Profile ID");
      const activities = await readRecords(activitiesPath);
      const matching = activities.filter(
        (activity) =>
          activity.profile_id === profileId &&
          (params.theme === undefined || activity.theme === params.theme),
      );
      return textResult(
        `Activities for profile_id ${profileId}${params.theme ? ` in theme ${params.theme}` : ""}:\n${formatInput({ activities: matching })}`,
      );
    },
  });
}
