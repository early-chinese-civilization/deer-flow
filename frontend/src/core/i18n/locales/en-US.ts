import {
  CompassIcon,
  GraduationCapIcon,
  ImageIcon,
  MicroscopeIcon,
  PenLineIcon,
  ShapesIcon,
  SparklesIcon,
  VideoIcon,
} from "lucide-react";

import type { Translations } from "./types";

export const enUS: Translations = {
  // Locale meta
  locale: {
    localName: "English",
  },

  // Common
  common: {
    home: "Home",
    settings: "Settings",
    delete: "Delete",
    edit: "Edit",
    rename: "Rename",
    share: "Share",
    openInNewWindow: "Open in new window",
    close: "Close",
    more: "More",
    search: "Search",
    download: "Download",
    thinking: "Thinking",
    artifacts: "Artifacts",
    public: "Public",
    custom: "Custom",
    notAvailableInDemoMode: "Not available in demo mode",
    loading: "Loading...",
    version: "Version",
    lastUpdated: "Last updated",
    code: "Code",
    preview: "Preview",
    cancel: "Cancel",
    save: "Save",
    previous: "Previous",
    next: "Next",
    install: "Install",
    create: "Create",
    import: "Import",
    export: "Export",
    exportAsMarkdown: "Export as Markdown",
    exportAsJSON: "Export as JSON",
    exportSuccess: "Conversation exported",
  },

  // Home
  home: {
    docs: "Docs",
    blog: "Blog",
  },

  // Welcome
  welcome: {
    greeting: "Hello, again!",
    description:
      "Welcome to 🦌 DeerFlow, an open source super agent. With built-in and custom skills, DeerFlow helps you search on the web, analyze data, and generate artifacts like slides, web pages and do almost anything.",

    createYourOwnSkill: "Create Your Own Skill",
    createYourOwnSkillDescription:
      "Create your own skill to release the power of DeerFlow. With customized skills,\nDeerFlow can help you search on the web, analyze data, and generate\n artifacts like slides, web pages and do almost anything.",
  },

  // Clipboard
  clipboard: {
    copyToClipboard: "Copy to clipboard",
    copiedToClipboard: "Copied to clipboard",
    failedToCopyToClipboard: "Failed to copy to clipboard",
    linkCopied: "Link copied to clipboard",
  },

  // Input Box
  inputBox: {
    placeholder: "How can I assist you today?",
    createSkillPrompt:
      "We're going to build a new skill step by step with `skill-creator`. To start, what do you want this skill to do?",
    addAttachments: "Add attachments",
    mode: "Mode",
    flashMode: "Flash",
    flashModeDescription: "Fast and efficient, but may not be accurate",
    reasoningMode: "Reasoning",
    reasoningModeDescription:
      "Reasoning before action, balance between time and accuracy",
    proMode: "Pro",
    proModeDescription:
      "Reasoning, planning and executing, get more accurate results, may take more time",
    ultraMode: "Ultra",
    ultraModeDescription:
      "Pro mode with subagents to divide work; best for complex multi-step tasks",
    reasoningEffort: "Reasoning Effort",
    reasoningEffortMinimal: "Minimal",
    reasoningEffortMinimalDescription: "Retrieval + Direct Output",
    reasoningEffortLow: "Low",
    reasoningEffortLowDescription: "Simple Logic Check + Shallow Deduction",
    reasoningEffortMedium: "Medium",
    reasoningEffortMediumDescription:
      "Multi-layer Logic Analysis + Basic Verification",
    reasoningEffortHigh: "High",
    reasoningEffortHighDescription:
      "Full-dimensional Logic Deduction + Multi-path Verification + Backward Check",
    searchModels: "Search models...",
    surpriseMe: "Surprise",
    surpriseMePrompt: "Surprise me",
    followupLoading: "Generating follow-up questions...",
    followupConfirmTitle: "Send suggestion?",
    followupConfirmDescription:
      "You already have text in the input. Choose how to send it.",
    followupConfirmAppend: "Append & send",
    followupConfirmReplace: "Replace & send",
    suggestions: [
      {
        suggestion: "Write",
        prompt: "Write a blog post about the latest trends on [topic]",
        icon: PenLineIcon,
      },
      {
        suggestion: "Research",
        prompt:
          "Conduct a deep dive research on [topic], and summarize the findings.",
        icon: MicroscopeIcon,
      },
      {
        suggestion: "Collect",
        prompt: "Collect data from [source] and create a report.",
        icon: ShapesIcon,
      },
      {
        suggestion: "Learn",
        prompt: "Learn about [topic] and create a tutorial.",
        icon: GraduationCapIcon,
      },
    ],
    suggestionsCreate: [
      {
        suggestion: "Webpage",
        prompt: "Create a webpage about [topic]",
        icon: CompassIcon,
      },
      {
        suggestion: "Image",
        prompt: "Create an image about [topic]",
        icon: ImageIcon,
      },
      {
        suggestion: "Video",
        prompt: "Create a video about [topic]",
        icon: VideoIcon,
      },
      {
        type: "separator",
      },
      {
        suggestion: "Skill",
        prompt:
          "We're going to build a new skill step by step with `skill-creator`. To start, what do you want this skill to do?",
        icon: SparklesIcon,
      },
    ],
  },

  // Sidebar
  sidebar: {
    newChat: "New chat",
    chats: "Chats",
    recentChats: "Recent chats",
    demoChats: "Demo chats",
    agents: "Agents",
    skills: "Skills",
  },

  // Agents
  agents: {
    title: "Agents",
    description:
      "Create and manage custom agents with specialized prompts and capabilities.",
    newAgent: "New Agent",
    emptyTitle: "No custom agents yet",
    emptyDescription:
      "Create your first custom agent with a specialized system prompt.",
    chat: "Chat",
    delete: "Delete",
    deleteConfirm:
      "Are you sure you want to delete this agent? This action cannot be undone.",
    deleteSuccess: "Agent deleted",
    newChat: "New chat",
    noAgent: "Default",
    selectAgent: "Choose agent",
    loadingAgent: "Resolving agent...",
    createPageTitle: "Design your Agent",
    createPageSubtitle:
      "Describe the agent you want — I'll help you create it through conversation.",
    nameStepTitle: "Name your new Agent",
    nameStepHint:
      "Letters, digits, and hyphens only — stored lowercase (e.g. code-reviewer)",
    nameStepPlaceholder: "e.g. code-reviewer",
    nameStepContinue: "Continue",
    nameStepInvalidError:
      "Invalid name — use only letters, digits, and hyphens",
    nameStepAlreadyExistsError: "An agent with this name already exists",
    nameStepNetworkError:
      "Network request failed — check your network or backend connection",
    nameStepCheckError: "Could not verify name availability — please try again",
    nameStepBootstrapMessage:
      "The new custom agent name is {name}. Let's bootstrap it's **SOUL**.",
    agentCreated: "Agent created!",
    startChatting: "Start chatting",
    backToGallery: "Back to Gallery",
    createPageDescription:
      "Configure the core information for your new agent before saving it.",
    createSectionName: "Name",
    createSectionDescription: "Description",
    createSectionSoul: "SOUL",
    createSectionSkills: "Skills",
    confirmSection: "Confirm",
    createNameTitle: "Choose an agent name",
    createNameHint:
      "Letters, digits, and hyphens only. The final name is stored in lowercase.",
    createDescriptionTitle: "Add a short description",
    createDescriptionHint:
      "This appears in the agent gallery and helps users understand what the agent does.",
    createSoulTitle: "Write the SOUL prompt",
    createSoulHint:
      "Use this area to define the agent's personality, boundaries, and working style.",
    createSkillsTitle: "Bind visible skills",
    createSkillsHint:
      "Select the skills this agent should use. Leave everything unchecked to create an agent without explicit skill bindings.",
    createSkillsEmpty: "No visible skills are available for this user yet.",
    createSkillsLoading: "Loading available skills...",
    skillSourceMySkills: "My Skills",
    skillSourceSkillHub: "SkillHub",
    skillSourceUnknown: "Unknown source",
    skillVersionUnavailable: "Version unavailable",
    skillUpdateAvailable: "Update available",
    skillMetadataUnavailable: "Skill metadata unavailable",
    enabledSkillsLabel: "Skills enabled",
    noBoundSkills: "No bound Skills",
    createButton: "Create agent",
    createButtonPending: "Creating...",
    createSuccess: "Agent created successfully.",
    createError: "Failed to create agent.",
    createNameRequiredError: "Agent name is required.",
    confirmTitle: "Review before submitting",
    confirmHint:
      "Draft changes stay local until you submit from this final tab.",
    confirmSubmitHint: "Only this tab publishes the final agent.",
    confirmEmptyValue: "Not provided yet",
    draftSaved: "Draft saved locally",
    resumeDraftError: "Could not restore this draft right now.",
    editPageTitle: "Edit agent",
    editPageDescription:
      "Update the core information and skill bindings for an existing agent.",
    editNameHint: "The agent name cannot be changed after creation.",
    updateButton: "Save changes",
    updateButtonPending: "Saving...",
    updateSuccess: "Agent updated successfully.",
    updateError: "Failed to update agent.",
  },

  // Breadcrumb
  breadcrumb: {
    workspace: "Workspace",
    chats: "Chats",
  },

  // Workspace
  workspace: {
    githubTooltip: "DeerFlow on Github",
    settingsAndMore: "Settings and more",
    logout: "Log out",
  },

  // Conversation
  conversation: {
    noMessages: "No messages yet",
    startConversation: "Start a conversation to see messages here",
  },

  // Chats
  chats: {
    searchChats: "Search chats",
  },

  // Page titles (document title)
  pages: {
    appName: "DeerFlow",
    chats: "Chats",
    newChat: "New chat",
    untitled: "Untitled",
  },

  // Tool calls
  toolCalls: {
    moreSteps: (count: number) => `${count} more step${count === 1 ? "" : "s"}`,
    lessSteps: "Less steps",
    executeCommand: "Execute command",
    presentFiles: "Present files",
    needYourHelp: "Need your help",
    useTool: (toolName: string) => `Use "${toolName}" tool`,
    searchFor: (query: string) => `Search for "${query}"`,
    searchForRelatedInfo: "Search for related information",
    searchForRelatedImages: "Search for related images",
    searchForRelatedImagesFor: (query: string) =>
      `Search for related images for "${query}"`,
    searchOnWebFor: (query: string) => `Search on the web for "${query}"`,
    viewWebPage: "View web page",
    listFolder: "List folder",
    readFile: "Read file",
    writeFile: "Write file",
    clickToViewContent: "Click to view file content",
    writeTodos: "Update to-do list",
    skillInstallTooltip: "Install skill and make it available to DeerFlow",
  },

  // Subtasks
  uploads: {
    uploading: "Uploading...",
    uploadingFiles: "Uploading files, please wait...",
    retry: "Retry",
    sendBlocked:
      "Wait for attachments to finish uploading, or remove failed files before sending.",
    deleteSuccess: "File deleted",
    deleteFailed: "Failed to delete file",
  },

  artifacts: {
    previewUnavailable: "Preview unavailable",
    previewUnavailableDescription: (fileType: string) =>
      `${fileType} files are not supported for inline preview yet. Download the file to view it locally.`,
    downloadFile: "Download file",
  },

  workspaceFiles: {
    title: "Workspace Files",
    files: "Files",
    refresh: "Refresh file list",
    searchPlaceholder: "Search files",
    loadFailed: "Failed to load files",
    noWorkspace: "No workspace available",
    noWorkspaceDescription:
      "This thread is not bound to a workspace_id yet, unable to read OSS file list.",
    noFiles: "No files in workspace",
    noFilesDescription: "Uploaded files will appear here.",
    noMatches: "No matching files",
    noMatchesDescription: "Try adjusting your search keywords.",
  },

  subtasks: {
    subtask: "Subtask",
    executing: (count: number) =>
      `Executing ${count === 1 ? "" : count + " "}subtask${count === 1 ? "" : "s in parallel"}`,
    in_progress: "Running subtask",
    completed: "Subtask completed",
    failed: "Subtask failed",
  },

  // Shortcuts
  shortcuts: {
    searchActions: "Search actions...",
    noResults: "No results found.",
    actions: "Actions",
    keyboardShortcuts: "Keyboard Shortcuts",
    keyboardShortcutsDescription:
      "Navigate DeerFlow faster with keyboard shortcuts.",
    openCommandPalette: "Open Command Palette",
    toggleSidebar: "Toggle Sidebar",
  },

  // Settings
  settings: {
    title: "Settings",
    description: "Adjust how DeerFlow looks and behaves for you.",
    sections: {
      appearance: "Appearance",
      memory: "Memory",
      tools: "Tools",
      skills: "Skills",
      notification: "Notification",
      about: "About",
    },
    memory: {
      title: "Memory",
      description:
        "DeerFlow automatically learns from your conversations in the background. These memories help DeerFlow understand you better and deliver a more personalized experience.",
      empty: "No memory data to display.",
      rawJson: "Raw JSON",
      exportButton: "Export memory",
      exportSuccess: "Memory exported",
      importButton: "Import memory",
      importConfirmTitle: "Import memory?",
      importConfirmDescription:
        "This will overwrite your current memory with the selected JSON backup.",
      importFileLabel: "Selected file",
      importInvalidFile:
        "Failed to read the selected memory file. Please choose a valid JSON export.",
      importSuccess: "Memory imported",
      manualFactSource: "Manual",
      addFact: "Add fact",
      addFactTitle: "Add memory fact",
      editFactTitle: "Edit memory fact",
      addFactSuccess: "Fact created",
      editFactSuccess: "Fact updated",
      clearAll: "Clear all memory",
      clearAllConfirmTitle: "Clear all memory?",
      clearAllConfirmDescription:
        "This will remove all saved summaries and facts. This action cannot be undone.",
      clearAllSuccess: "All memory cleared",
      factDeleteConfirmTitle: "Delete this fact?",
      factDeleteConfirmDescription:
        "This fact will be removed from memory immediately. This action cannot be undone.",
      factDeleteSuccess: "Fact deleted",
      factContentLabel: "Content",
      factCategoryLabel: "Category",
      factConfidenceLabel: "Confidence",
      factContentPlaceholder: "Describe the memory fact you want to save",
      factCategoryPlaceholder: "context",
      factConfidenceHint: "Use a number between 0 and 1.",
      factSave: "Save fact",
      factValidationContent: "Fact content cannot be empty.",
      factValidationConfidence: "Confidence must be a number between 0 and 1.",
      noFacts: "No saved facts yet.",
      summaryReadOnly:
        "Summary sections are read-only for now. You can currently add, edit, or delete individual facts, or clear all memory.",
      memoryFullyEmpty: "No memory saved yet.",
      factPreviewLabel: "Fact to delete",
      searchPlaceholder: "Search memory",
      filterAll: "All",
      filterFacts: "Facts",
      filterSummaries: "Summaries",
      noMatches: "No matching memory found.",
      markdown: {
        overview: "Overview",
        userContext: "User context",
        work: "Work",
        personal: "Personal",
        topOfMind: "Top of mind",
        historyBackground: "History",
        recentMonths: "Recent months",
        earlierContext: "Earlier context",
        longTermBackground: "Long-term background",
        updatedAt: "Updated at",
        facts: "Facts",
        empty: "(empty)",
        table: {
          category: "Category",
          confidence: "Confidence",
          confidenceLevel: {
            veryHigh: "Very high",
            high: "High",
            normal: "Normal",
            unknown: "Unknown",
          },
          content: "Content",
          source: "Source",
          createdAt: "CreatedAt",
          view: "View",
        },
      },
    },
    appearance: {
      themeTitle: "Theme",
      themeDescription:
        "Choose how the interface follows your device or stays fixed.",
      system: "System",
      light: "Light",
      dark: "Dark",
      systemDescription: "Match the operating system preference automatically.",
      lightDescription: "Bright palette with higher contrast for daytime.",
      darkDescription: "Dim palette that reduces glare for focus.",
      languageTitle: "Language",
      languageDescription: "Switch between languages.",
    },
    tools: {
      title: "Tools",
      description: "Manage the configuration and enabled status of MCP tools.",
    },
    skills: {
      title: "Skills",
      description:
        "Install Skills from SkillHub and manage the Skills in your workspace.",
      createSkill: "Create skill",
      emptyTitle: "No Skills yet",
      emptyDescription:
        "Install Skills from SkillHub or upload your own Skill to My Skills.",
      emptyButton: "Create Your First Skill",
      uploadSkill: "Upload skills",
      uploadPending: "Uploading...",
      uploadSuccess: "Skills uploaded successfully.",
      uploadError: "Failed to upload skills.",
      publishSkill: "Publish",
      installSkill: "Install",
      installPending: "Installing...",
      installSuccess: (skillName: string) =>
        `Skill "${skillName}" installed successfully.`,
      installError: "Failed to install Skill.",
      publishSuccess: (skillName: string) =>
        `Skill "${skillName}" published successfully.`,
      publishPending: "Publishing...",
      viewUpdate: "View update",
      updateSuccess: (skillName: string) =>
        `Skill "${skillName}" updated successfully.`,
      updateError: "Failed to update installed Skill.",
      updatePending: "Updating...",
      publishedBy: (ownerDisplayName: string) =>
        `Published by ${ownerDisplayName}`,
      skillHubTab: "SkillHub",
      mySkillsTab: "My Skills",
      communitySpaceTab: "Community Space",
      personalSpaceTab: "Personal Space",
      allSegment: "All",
      downloadedSegment: "Added",
      authoredSegment: "My Skills",
      publishedSegment: "Published",
      updatesSegment: "Updates",
      forksSegment: "Forks",
      platformVersion: (version: number) => `Version ${version}`,
      skillHubVersion: (version: number) => `SkillHub version ${version}`,
      currentVersion: (version: number) => `Current version ${version}`,
      currentAndUpdateVersions: (
        currentVersion: number,
        latestVersion: number,
      ) =>
        `Current version ${currentVersion}; update to version ${latestVersion}`,
      noPlatformVersion: "No platform version yet",
      installed: "Installed",
      notInstalled: "Not installed",
      updateAvailable: "Update available",
      availableInCommunity: "Available in Community Space",
      downloadedToPersonal: "Added to Personal Space",
      published: "Published",
      unpublished: "Not published",
      unpublishedChanges: "Unpublished changes",
      mySkill: "My Skill",
      publishedByYou: "Published by you",
      forkedSkill: "Forked Skill",
      officialSource: "Official Skill",
      communitySpaceSource: "Community",
      communitySource: (ownerDisplayName: string) =>
        `Community Skill by ${ownerDisplayName}`,
      downloadedSource: (ownerDisplayName: string) =>
        `From ${ownerDisplayName} in Community Space`,
      forkedSource: (ownerDisplayName: string) =>
        `Based on ${ownerDisplayName}`,
      installedSource: "Added to Personal Space",
      createdSource: "My Skill in Personal Space",
      addToPersonalSpace: "Add to Personal Space",
      viewInPersonalSpace: "View in Personal Space",
      managePublished: "Manage published version",
      publishUpdate: "Publish update",
      publishDialogTitle: "Publish skill",
      publishDialogDescription:
        "Review the Skill before publishing it to SkillHub.",
      publishDescriptionLabel: "Description",
      releaseNotesLabel: "Release notes (optional)",
      releaseNotesPlaceholder: "What changed in this publish?",
      releaseNotesHelp:
        "These notes will be shown to SkillHub users for this platform version.",
      publishAsLatestNotice:
        "Publishing creates a SkillHub version snapshot that other users can install.",
      confirmPublish: "Publish to SkillHub",
      updateDialogTitle: "Review Skill update",
      updateDialogDescription:
        "Confirming changes the installed version for future Agent runs.",
      updatePreviewLoading: "Loading update preview...",
      currentVersionLabel: "Current version",
      availableVersionLabel: "Available version",
      sourceLabel: "Source",
      publisherLabel: "Publisher",
      publishedAtLabel: "Published",
      unknownPublisher: "Unknown publisher",
      affectedAgentsLabel: "Affected Agents",
      noAffectedAgents: "No Agents are currently bound to this Skill.",
      noReleaseNotes: "No release notes were provided.",
      confirmUpdate: "Update installed Skill",
      deleteBlocked: (agentName: string) =>
        `This skill is bound to agent "${agentName}" and cannot be deleted.`,
      conflictConfirm: (skillName: string) =>
        `Skill "${skillName}" already exists. Do you want to overwrite it?`,
      noMySkills: "No Skills in your workspace yet.",
      noSkillHubSkills: "No SkillHub Skills available.",
    },
    notification: {
      title: "Notification",
      description:
        "DeerFlow only sends a completion notification when the window is not active. This is especially useful for long-running tasks so you can switch to other work and get notified when done.",
      requestPermission: "Request notification permission",
      deniedHint:
        "Notification permission was denied. You can enable it in your browser's site settings to receive completion alerts.",
      testButton: "Send test notification",
      testTitle: "DeerFlow",
      testBody: "This is a test notification.",
      notSupported: "Your browser does not support notifications.",
      disableNotification: "Disable notification",
    },
    acknowledge: {
      emptyTitle: "Acknowledgements",
      emptyDescription: "Credits and acknowledgements will show here.",
    },
  },
};
