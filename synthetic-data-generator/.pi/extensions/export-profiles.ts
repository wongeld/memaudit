import { readFile } from "node:fs/promises";
import { isAbsolute, resolve } from "node:path";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { Type } from "typebox";

const requiredColumns = [
  "profile_id",
  "identifiers_first_name",
  "identifiers_last_name",
  "identifiers_email",
  "identifiers_phone_number",
  "identifiers_national_id",
  "identifiers_national_id_format_note",
  "identifiers_country",
  "personal_attributes_age",
  "personal_attributes_location",
  "personal_attributes_occupation",
  "personal_attributes_education_level",
  "personal_attributes_family_status",
  "personal_attributes_health_condition",
  "domain_metadata_primary_domain",
  "domain_metadata_active_scenarios",
] as const;

function parseCsv(text: string): string[][] {
  const rows: string[][] = [];
  let row: string[] = [];
  let field = "";
  let inQuotes = false;

  for (let index = 0; index < text.length; index += 1) {
    const character = text[index];

    if (inQuotes) {
      if (character === '"' && text[index + 1] === '"') {
        field += '"';
        index += 1;
      } else if (character === '"') {
        inQuotes = false;
      } else {
        field += character;
      }
    } else if (character === '"' && field.length === 0) {
      inQuotes = true;
    } else if (character === ",") {
      row.push(field);
      field = "";
    } else if (character === "\n" || character === "\r") {
      if (character === "\r" && text[index + 1] === "\n") index += 1;
      row.push(field);
      field = "";
      if (row.some((value) => value.length > 0)) rows.push(row);
      row = [];
    } else {
      field += character;
    }
  }

  if (inQuotes) throw new Error("CSV contains an unterminated quoted field.");
  if (field.length > 0 || row.length > 0) {
    row.push(field);
    if (row.some((value) => value.length > 0)) rows.push(row);
  }

  return rows;
}

function getValue(
  row: Record<string, string>,
  column: (typeof requiredColumns)[number],
  rowNumber: number,
): string {
  const value = row[column];
  if (value === undefined || value.trim() === "") {
    throw new Error(
      `CSV row ${rowNumber} has an empty required field: ${column}.`,
    );
  }
  return value;
}

function convertCsvToProfiles(text: string): object[] {
  const [headerRow, ...dataRows] = parseCsv(text);
  if (!headerRow) throw new Error("The CSV file is empty.");

  const headers = headerRow.map((header, index) =>
    index === 0 ? header.replace(/^\uFEFF/, "") : header,
  );
  const missingColumns = requiredColumns.filter(
    (column) => !headers.includes(column),
  );
  if (missingColumns.length > 0) {
    throw new Error(
      `CSV is missing required columns: ${missingColumns.join(", ")}.`,
    );
  }

  return dataRows.map((values, index) => {
    const rowNumber = index + 2;
    if (values.length !== headers.length) {
      throw new Error(
        `CSV row ${rowNumber} has ${values.length} fields; expected ${headers.length}.`,
      );
    }

    const row = Object.fromEntries(
      headers.map((header, i) => [header, values[i]]),
    );
    const ageText = getValue(row, "personal_attributes_age", rowNumber);
    const age = Number(ageText);
    if (!Number.isInteger(age)) {
      throw new Error(
        `CSV row ${rowNumber} has an invalid integer age: ${ageText}.`,
      );
    }

    let activeScenarios: unknown;
    try {
      activeScenarios = JSON.parse(
        getValue(row, "domain_metadata_active_scenarios", rowNumber),
      );
    } catch (error) {
      throw new Error(
        `CSV row ${rowNumber} has invalid active-scenarios JSON.`,
        {
          cause: error,
        },
      );
    }
    if (
      !Array.isArray(activeScenarios) ||
      !activeScenarios.every((scenario) => typeof scenario === "string")
    ) {
      throw new Error(
        `CSV row ${rowNumber} active scenarios must be an array of strings.`,
      );
    }

    return {
      profile_id: getValue(row, "profile_id", rowNumber),
      identifiers: {
        first_name: getValue(row, "identifiers_first_name", rowNumber),
        last_name: getValue(row, "identifiers_last_name", rowNumber),
        email: getValue(row, "identifiers_email", rowNumber),
        phone_number: getValue(row, "identifiers_phone_number", rowNumber),
        national_id: getValue(row, "identifiers_national_id", rowNumber),
        national_id_format_note: getValue(
          row,
          "identifiers_national_id_format_note",
          rowNumber,
        ),
        country: getValue(row, "identifiers_country", rowNumber),
      },
      personal_attributes: {
        age,
        location: getValue(row, "personal_attributes_location", rowNumber),
        occupation: getValue(row, "personal_attributes_occupation", rowNumber),
        education_level: getValue(
          row,
          "personal_attributes_education_level",
          rowNumber,
        ),
        family_status: getValue(
          row,
          "personal_attributes_family_status",
          rowNumber,
        ),
        health_condition: getValue(
          row,
          "personal_attributes_health_condition",
          rowNumber,
        ),
      },
      domain_metadata: {
        primary_domain: getValue(
          row,
          "domain_metadata_primary_domain",
          rowNumber,
        ),
        active_scenarios: activeScenarios,
      },
    };
  });
}

export default function (pi: ExtensionAPI) {
  pi.registerTool({
    name: "export_profiles_as_json",
    label: "Export profiles as JSON",
    description:
      "Convert every profile row in a CSV file into one JSON array using the nested profile schema. Use when asked to get all user profiles.",
    parameters: Type.Object({
      csv_path: Type.Optional(
        Type.String({
          description:
            "CSV file path relative to the workspace root; defaults to profiles/users.csv.",
        }),
      ),
    }),
    async execute(_toolCallId, params) {
      const csvPath = params.csv_path
        ? isAbsolute(params.csv_path)
          ? params.csv_path
          : resolve(process.cwd(), params.csv_path)
        : resolve(process.cwd(), "profiles", "users.csv");
      const csvText = await readFile(csvPath, "utf8");
      const profiles = convertCsvToProfiles(csvText);

      return {
        content: [{ type: "text", text: JSON.stringify(profiles, null, 2) }],
        details: { profile_count: profiles.length, csv_path: csvPath },
      };
    },
  });
}
