import AppIntents

/// Apple Watch Ultra's Action button. Choosing XGSail under Settings → Action
/// Button → Workout makes the first press run `StartSailingIntent`; from then
/// on, for as long as the workout lives, each press runs whatever intent the
/// previous one returned via `.result(actionButtonIntent:)` — here always
/// `RaceActionIntent`, which acts on the race's current state
/// (`Sailing.actionButton`). Action + side button pauses and resumes, the
/// system convention, through the pause/resume intents.

enum SailingStyle: String, AppEnum {
    case regatta, outing

    static let typeDisplayRepresentation: TypeDisplayRepresentation = "Sailing"
    static let caseDisplayRepresentations: [SailingStyle: DisplayRepresentation] = [
        .regatta: DisplayRepresentation(title: "Regatta start", image: .init(systemName: "flag.checkered")),
        .outing: DisplayRepresentation(title: "Outing", image: .init(systemName: "sailboat.fill")),
    ]
}

struct StartSailingIntent: StartWorkoutIntent {
    static let title: LocalizedStringResource = "Start sailing"
    static let suggestedWorkouts: [StartSailingIntent] = [
        StartSailingIntent(style: .regatta),
        StartSailingIntent(style: .outing),
    ]

    @Parameter(title: "Style")
    var workoutStyle: SailingStyle

    var displayRepresentation: DisplayRepresentation {
        SailingStyle.caseDisplayRepresentations[workoutStyle] ?? "Sailing"
    }

    init() {}

    @MainActor
    func perform() async throws -> some IntentResult {
        let sailing = Sailing.shared
        switch workoutStyle {
        case .regatta: sailing.startSequence(minutes: sailing.race.sequenceMinutes)
        case .outing: sailing.startOuting()
        }
        return .result(actionButtonIntent: RaceActionIntent())
    }
}

/// Every press after the first: start / sync / finish, by race state.
struct RaceActionIntent: AppIntent {
    static let title: LocalizedStringResource = "Race action"
    static let isDiscoverable = false

    @MainActor
    func perform() async throws -> some IntentResult {
        Sailing.shared.actionButton()
        return .result(actionButtonIntent: RaceActionIntent())
    }
}

struct PauseSailingIntent: PauseWorkoutIntent {
    static let title: LocalizedStringResource = "Pause recording"

    @MainActor
    func perform() async throws -> some IntentResult {
        Sailing.shared.recorder.pause()
        return .result()
    }
}

struct ResumeSailingIntent: ResumeWorkoutIntent {
    static let title: LocalizedStringResource = "Resume recording"

    @MainActor
    func perform() async throws -> some IntentResult {
        Sailing.shared.recorder.resume()
        return .result()
    }
}
