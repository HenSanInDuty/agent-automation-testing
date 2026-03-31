"use client";

import * as React from "react";
import { useForm, Controller } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Brain, Eye, EyeOff, Wifi, WifiOff, Check } from "lucide-react";

import {
  Modal,
  ModalHeader,
  ModalBody,
  ModalFooter,
  ModalDivider,
} from "@/components/ui/Modal";
import { Button } from "@/components/ui/Button";
import { FormField, Label } from "@/components/ui/Input";
import { SelectField, Toggle } from "@/components/ui/Select";
import { toast } from "@/components/ui/Toast";
import {
  useCreateLLMProfile,
  useUpdateLLMProfile,
  useTestLLMProfile,
} from "@/hooks/useLLMProfiles";
import {
  LLMProvider,
  LLM_PROVIDER_LABELS,
  PROVIDER_MODELS,
  PROVIDERS_REQUIRING_API_KEY,
  PROVIDERS_REQUIRING_BASE_URL,
  type LLMProfileResponse,
  type LLMProfileCreate,
  type LLMProfileUpdate,
} from "@/types";
import { cn } from "@/lib/utils";

// ─────────────────────────────────────────────────────────────────────────────
// Zod schema
// ─────────────────────────────────────────────────────────────────────────────

const schema = z.object({
  name: z
    .string()
    .min(1, "Name is required")
    .max(100, "Name must be 100 characters or less"),
  provider: z.nativeEnum(LLMProvider),
  model: z
    .string()
    .min(1, "Model is required")
    .max(150, "Model name must be 150 characters or less"),
  api_key: z.string().optional().nullable(),
  base_url: z.string().optional().nullable(),
  temperature: z
    .number()
    .min(0, "Minimum value is 0")
    .max(2, "Maximum value is 2"),
  max_tokens: z
    .number()
    .int("Must be a whole number")
    .min(1, "Minimum value is 1")
    .max(128000, "Maximum value is 128,000"),
  is_default: z.boolean(),
});

type FormValues = z.infer<typeof schema>;

// ─────────────────────────────────────────────────────────────────────────────
// Props
// ─────────────────────────────────────────────────────────────────────────────

interface LLMProfileDialogProps {
  open: boolean;
  onClose: () => void;
  profile?: LLMProfileResponse;
}

// ─────────────────────────────────────────────────────────────────────────────
// Helper: build default form values
// ─────────────────────────────────────────────────────────────────────────────

function buildDefaultValues(profile?: LLMProfileResponse): FormValues {
  if (profile) {
    return {
      name: profile.name,
      provider: profile.provider,
      model: profile.model,
      api_key: null, // never pre-populate the masked key
      base_url: profile.base_url ?? null,
      temperature: profile.temperature,
      max_tokens: profile.max_tokens,
      is_default: profile.is_default,
    };
  }
  return {
    name: "",
    provider: LLMProvider.OPENAI,
    model: "",
    api_key: null,
    base_url: null,
    temperature: 0.7,
    max_tokens: 4096,
    is_default: false,
  };
}

// ─────────────────────────────────────────────────────────────────────────────
// Sub-component: styled number input + label + hint/error
// ─────────────────────────────────────────────────────────────────────────────

interface NumberInputFieldProps {
  id: string;
  label: string;
  hint?: string;
  error?: string;
  step?: number;
  min?: number;
  max?: number;
  placeholder?: string;
  // react-hook-form register return value
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  registration: Record<string, any>;
}

function NumberInputField({
  id,
  label,
  hint,
  error,
  step,
  min,
  max,
  placeholder,
  registration,
}: NumberInputFieldProps) {
  return (
    <div className="flex flex-col">
      <label
        htmlFor={id}
        className="block text-sm font-medium text-[#92a4c9] mb-1.5 select-none"
      >
        {label}
      </label>
      <input
        id={id}
        type="number"
        step={step}
        min={min}
        max={max}
        placeholder={placeholder}
        className={cn(
          "w-full h-9 rounded-lg bg-[#101622] border text-sm text-white px-3",
          "placeholder:text-[#3d5070] transition-colors duration-150",
          "outline-none focus:ring-2 focus:ring-[#135bec] focus:ring-offset-0",
          error
            ? "border-[#ef4444] focus:ring-[#ef4444]"
            : "border-[#2b3b55] focus:border-[#135bec]",
          "disabled:opacity-50 disabled:cursor-not-allowed"
        )}
        {...registration}
      />
      {error ? (
        <p className="mt-1.5 text-xs text-[#ef4444]" role="alert">
          {error}
        </p>
      ) : hint ? (
        <p className="mt-1.5 text-xs text-[#3d5070]">{hint}</p>
      ) : null}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Sub-component: test result banner
// ─────────────────────────────────────────────────────────────────────────────

interface TestResult {
  success: boolean;
  message: string;
  latency_ms?: number | null;
}

function TestResultBanner({ success, message, latency_ms }: TestResult) {
  return (
    <div
      role="status"
      aria-live="polite"
      className={cn(
        "flex items-start gap-2.5 px-3.5 py-3 rounded-lg border text-sm",
        success
          ? "bg-[#22c55e]/10 border-[#22c55e]/30 text-[#4ade80]"
          : "bg-[#ef4444]/10 border-[#ef4444]/30 text-[#f87171]"
      )}
    >
      <span className="shrink-0 mt-0.5">
        {success ? (
          <Check className="w-4 h-4" aria-hidden="true" />
        ) : (
          <WifiOff className="w-4 h-4" aria-hidden="true" />
        )}
      </span>
      <div className="min-w-0 flex-1">
        <p className="font-semibold leading-snug">
          {success ? "Connection successful" : "Connection failed"}
        </p>
        <p className="text-xs mt-0.5 opacity-80 break-words leading-relaxed">
          {message}
        </p>
        {success && latency_ms != null && (
          <p className="text-xs mt-1 opacity-60 font-mono">
            {latency_ms.toFixed(0)} ms latency
          </p>
        )}
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// LLMProfileDialog
// ─────────────────────────────────────────────────────────────────────────────

export function LLMProfileDialog({
  open,
  onClose,
  profile,
}: LLMProfileDialogProps) {
  const isEdit = Boolean(profile);

  // ── Local UI state ───────────────────────────────────────────────────────
  const [showApiKey, setShowApiKey] = React.useState(false);
  const [testResult, setTestResult] = React.useState<TestResult | null>(null);

  // ── Mutations ────────────────────────────────────────────────────────────
  const createMutation = useCreateLLMProfile();
  const updateMutation = useUpdateLLMProfile();
  const testMutation = useTestLLMProfile();

  // ── Form ─────────────────────────────────────────────────────────────────
  const {
    register,
    handleSubmit,
    control,
    watch,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: buildDefaultValues(profile),
  });

  const selectedProvider = watch("provider");
  const needsApiKey = PROVIDERS_REQUIRING_API_KEY.includes(selectedProvider);
  const needsBaseUrl = PROVIDERS_REQUIRING_BASE_URL.includes(selectedProvider);

  // Reset form & UI state when the dialog opens or the profile prop changes
  React.useEffect(() => {
    if (open) {
      reset(buildDefaultValues(profile));
      setTestResult(null);
      setShowApiKey(false);
    }
  }, [open, profile, reset]);

  // ── Derived ──────────────────────────────────────────────────────────────
  const providerOptions = (
    Object.entries(LLM_PROVIDER_LABELS) as [LLMProvider, string][]
  ).map(([value, label]) => ({ value, label }));

  const modelSuggestions: string[] = PROVIDER_MODELS[selectedProvider] ?? [];
  const datalistId = "llm-profile-model-datalist";

  // ── Handlers ─────────────────────────────────────────────────────────────
  const handleTest = async () => {
    if (!profile?.id) return;
    setTestResult(null);
    try {
      const result = await testMutation.mutateAsync({ id: profile.id });
      setTestResult({
        success: result.success,
        message: result.message,
        latency_ms: result.latency_ms,
      });
    } catch {
      setTestResult({
        success: false,
        message: "Connection test failed. Check your configuration and try again.",
      });
    }
  };

  const onSubmit = async (values: FormValues) => {
    // Re-derive provider requirements at submit time (uses submitted values)
    const requiresApiKey = PROVIDERS_REQUIRING_API_KEY.includes(values.provider);
    const requiresBaseUrl = PROVIDERS_REQUIRING_BASE_URL.includes(values.provider);

    const cleanApiKey = requiresApiKey
      ? values.api_key?.trim() || null
      : null;
    const cleanBaseUrl = requiresBaseUrl
      ? values.base_url?.trim() || null
      : null;

    try {
      if (isEdit && profile) {
        const payload: LLMProfileUpdate = {
          name: values.name,
          provider: values.provider,
          model: values.model,
          base_url: cleanBaseUrl,
          temperature: values.temperature,
          max_tokens: values.max_tokens,
          is_default: values.is_default,
          // Only include api_key if the user typed a new value
          ...(cleanApiKey ? { api_key: cleanApiKey } : {}),
        };
        await updateMutation.mutateAsync({ id: profile.id, payload });
        toast.success("Profile updated", `"${values.name}" has been saved.`);
      } else {
        const payload: LLMProfileCreate = {
          name: values.name,
          provider: values.provider,
          model: values.model,
          api_key: cleanApiKey,
          base_url: cleanBaseUrl,
          temperature: values.temperature,
          max_tokens: values.max_tokens,
          is_default: values.is_default,
        };
        await createMutation.mutateAsync(payload);
        toast.success(
          "Profile created",
          `"${values.name}" is ready to use.`
        );
      }
      onClose();
    } catch (err: unknown) {
      const detail = (
        err as { response?: { data?: { detail?: unknown } } }
      )?.response?.data?.detail;
      const message =
        typeof detail === "string"
          ? detail
          : "An unexpected error occurred. Please try again.";
      toast.error(isEdit ? "Update failed" : "Create failed", message);
    }
  };

  const isBusy =
    isSubmitting || createMutation.isPending || updateMutation.isPending;
  const isTesting = testMutation.isPending;

  // Safe close — no-op while a mutation is running
  const handleClose = () => {
    if (!isBusy) onClose();
  };

  // ── Render ────────────────────────────────────────────────────────────────
  return (
    <Modal open={open} onClose={handleClose} size="lg" disableBackdropClose={isBusy}>
      <ModalHeader
        title={isEdit ? "Edit LLM Profile" : "New LLM Profile"}
        subtitle={
          isEdit
            ? `Editing "${profile?.name}"`
            : "Configure a language model provider for your agents"
        }
        icon={<Brain className="w-5 h-5" aria-hidden="true" />}
        onClose={isBusy ? undefined : handleClose}
      />

      <form onSubmit={handleSubmit(onSubmit)} noValidate>
        <ModalBody>
          <div className="space-y-5">

            {/* ── Profile Name ─────────────────────────────────────────────── */}
            <FormField
              id="llm-name"
              label="Profile Name"
              required
              placeholder='e.g. "GPT-4o Production"'
              error={errors.name?.message}
              {...register("name")}
            />

            {/* ── Provider ─────────────────────────────────────────────────── */}
            <Controller
              name="provider"
              control={control}
              render={({ field }) => (
                <SelectField
                  id="llm-provider"
                  label="Provider"
                  required
                  options={providerOptions}
                  value={field.value}
                  onChange={(e) => {
                    field.onChange(e.target.value as LLMProvider);
                    // Clear stale test result when provider changes
                    setTestResult(null);
                  }}
                  error={errors.provider?.message}
                />
              )}
            />

            {/* ── Model ────────────────────────────────────────────────────── */}
            <div className="flex flex-col">
              <Label htmlFor="llm-model" required>
                Model
              </Label>
              <input
                id="llm-model"
                list={datalistId}
                autoComplete="off"
                placeholder={
                  modelSuggestions[0]
                    ? `e.g. ${modelSuggestions[0]}`
                    : "Enter model identifier…"
                }
                className={cn(
                  "w-full h-9 rounded-lg bg-[#101622] border text-sm text-white px-3",
                  "placeholder:text-[#3d5070] transition-colors duration-150",
                  "outline-none focus:ring-2 focus:ring-[#135bec] focus:ring-offset-0",
                  errors.model
                    ? "border-[#ef4444] focus:ring-[#ef4444]"
                    : "border-[#2b3b55] focus:border-[#135bec]",
                  "disabled:opacity-50 disabled:cursor-not-allowed"
                )}
                {...register("model")}
              />
              <datalist id={datalistId}>
                {modelSuggestions.map((m) => (
                  <option key={m} value={m} />
                ))}
              </datalist>
              {errors.model ? (
                <p className="mt-1.5 text-xs text-[#ef4444]" role="alert">
                  {errors.model.message}
                </p>
              ) : modelSuggestions.length > 0 ? (
                <p className="mt-1.5 text-xs text-[#3d5070]">
                  Start typing or pick from the suggested models
                </p>
              ) : null}
            </div>

            {/* ── API Key ──────────────────────────────────────────────────── */}
            {needsApiKey && (
              <div className="flex flex-col">
                <Label htmlFor="llm-api-key">API Key</Label>
                <div className="relative flex items-center">
                  <input
                    id="llm-api-key"
                    type={showApiKey ? "text" : "password"}
                    placeholder={
                      isEdit && profile?.api_key
                        ? "sk-••••••••"
                        : "sk-…"
                    }
                    autoComplete="new-password"
                    className={cn(
                      "w-full h-9 rounded-lg bg-[#101622] border text-sm text-white",
                      "pl-3 pr-10",
                      "placeholder:text-[#3d5070] transition-colors duration-150",
                      "outline-none focus:ring-2 focus:ring-[#135bec] focus:ring-offset-0",
                      errors.api_key
                        ? "border-[#ef4444] focus:ring-[#ef4444]"
                        : "border-[#2b3b55] focus:border-[#135bec]",
                      "disabled:opacity-50 disabled:cursor-not-allowed"
                    )}
                    {...register("api_key")}
                  />
                  <button
                    type="button"
                    onClick={() => setShowApiKey((v) => !v)}
                    tabIndex={0}
                    aria-label={showApiKey ? "Hide API key" : "Show API key"}
                    className={cn(
                      "absolute right-3 p-0.5 rounded",
                      "text-[#92a4c9] hover:text-white transition-colors duration-150",
                      "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#135bec]"
                    )}
                  >
                    {showApiKey ? (
                      <EyeOff className="w-4 h-4" aria-hidden="true" />
                    ) : (
                      <Eye className="w-4 h-4" aria-hidden="true" />
                    )}
                  </button>
                </div>
                {errors.api_key ? (
                  <p className="mt-1.5 text-xs text-[#ef4444]" role="alert">
                    {errors.api_key.message}
                  </p>
                ) : isEdit ? (
                  <p className="mt-1.5 text-xs text-[#3d5070]">
                    Leave blank to keep the current key
                  </p>
                ) : null}
              </div>
            )}

            {/* ── Base URL ─────────────────────────────────────────────────── */}
            {needsBaseUrl && (
              <FormField
                id="llm-base-url"
                label="Base URL"
                placeholder={
                  selectedProvider === LLMProvider.OLLAMA
                    ? "http://localhost:11434"
                    : "https://your-resource.openai.azure.com"
                }
                hint="The endpoint URL for the provider API"
                error={errors.base_url?.message}
                {...register("base_url")}
              />
            )}

            {/* ── Separator ────────────────────────────────────────────────── */}
            <ModalDivider />

            {/* ── Temperature + Max Tokens ─────────────────────────────────── */}
            <div className="grid grid-cols-2 gap-4">
              <NumberInputField
                id="llm-temperature"
                label="Temperature"
                step={0.1}
                min={0}
                max={2}
                placeholder="0.7"
                hint="Controls randomness · 0.0 – 2.0"
                error={errors.temperature?.message}
                registration={register("temperature", { valueAsNumber: true })}
              />
              <NumberInputField
                id="llm-max-tokens"
                label="Max Tokens"
                step={1}
                min={1}
                max={128000}
                placeholder="4096"
                hint="Max output length · up to 128,000"
                error={errors.max_tokens?.message}
                registration={register("max_tokens", { valueAsNumber: true })}
              />
            </div>

            {/* ── Is Default ───────────────────────────────────────────────── */}
            <Controller
              name="is_default"
              control={control}
              render={({ field }) => (
                <div
                  className={cn(
                    "flex items-center justify-between gap-4",
                    "px-4 py-3 rounded-lg",
                    "border border-[#2b3b55] bg-[#101622]/60",
                    "transition-colors duration-150",
                    field.value && "border-[#135bec]/40 bg-[#135bec]/5"
                  )}
                >
                  <div className="min-w-0">
                    <p className="text-sm font-medium text-white leading-snug">
                      Set as Default
                    </p>
                    <p className="mt-0.5 text-xs text-[#92a4c9] leading-snug">
                      Use this profile by default across all agents
                    </p>
                  </div>
                  <Toggle
                    id="llm-is-default"
                    checked={field.value}
                    onChange={field.onChange}
                  />
                </div>
              )}
            />

            {/* ── Test Connection (edit mode only) ─────────────────────────── */}
            {isEdit && profile?.id && (
              <>
                <ModalDivider />
                <div className="space-y-3">
                  <div className="flex items-start justify-between gap-4">
                    <div className="min-w-0">
                      <p className="text-sm font-medium text-white leading-snug">
                        Test Connection
                      </p>
                      <p className="mt-0.5 text-xs text-[#92a4c9] leading-snug">
                        Verify that the saved configuration can reach the
                        provider
                      </p>
                    </div>
                    <Button
                      type="button"
                      variant="secondary"
                      size="sm"
                      loading={isTesting}
                      disabled={isTesting || isBusy}
                      leftIcon={
                        <Wifi className="w-3.5 h-3.5" aria-hidden="true" />
                      }
                      onClick={handleTest}
                      className="shrink-0"
                    >
                      Test
                    </Button>
                  </div>

                  {testResult && (
                    <TestResultBanner
                      success={testResult.success}
                      message={testResult.message}
                      latency_ms={testResult.latency_ms}
                    />
                  )}
                </div>
              </>
            )}

          </div>
        </ModalBody>

        <ModalFooter>
          <Button
            type="button"
            variant="ghost"
            onClick={handleClose}
            disabled={isBusy}
          >
            Cancel
          </Button>
          <Button
            type="submit"
            variant="primary"
            loading={isBusy}
            disabled={isBusy}
          >
            {isEdit ? "Save Changes" : "Create Profile"}
          </Button>
        </ModalFooter>
      </form>
    </Modal>
  );
}

export default LLMProfileDialog;
