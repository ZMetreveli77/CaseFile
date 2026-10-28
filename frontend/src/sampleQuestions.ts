// One question per outcome, so a first-time visitor can see each behaviour. The first is the assignment's example,
// asked of the Larkspur Payments scenario (data/scenario); the others come from the evaluation set.
export interface SampleQuestion {
  question: string
  outcome: string // what the visitor should expect
}

export const SAMPLE_QUESTIONS: SampleQuestion[] = [
  {
    question: 'Which system changes caused payment processing delays in March, which services were affected, '
      + 'and which documents confirm it?',
    outcome: 'Company documents: change log + incident reports',
  },
  {
    question: 'Jim Halsey guided the career of the musician who hosted what country variety show?',
    outcome: 'Multi-hop: connects two documents',
  },
  {
    question: 'In which year was the liberal weekly newspaper La Voz del Pueblo published in Bogotá?',
    outcome: 'Sources conflict',
  },
  {
    question: 'Who won the 2030 FIFA World Cup?',
    outcome: 'No evidence: CaseFile declines',
  },
]
