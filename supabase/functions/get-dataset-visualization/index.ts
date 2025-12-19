// Edge Function to generate beta diversity visualization data
// @ts-ignore
import * as postgres from 'https://deno.land/x/postgres@v0.17.0/mod.ts'

const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
}

// Calculate Bray-Curtis dissimilarity between two samples
function brayCurtisDistance(sample1: number[], sample2: number[]): number {
  let lesser_count = 0
  let total_count_sample1 = 0
  let total_count_sample2 = 0

  for (let i = 0; i < sample1.length; i++) {
    lesser_count += Math.min(sample1[i], sample2[i])
    total_count_sample1 += sample1[i]
    total_count_sample2 += sample2[i]
  }

  // Make sure we don't divide by zero
  if (total_count_sample1 === 0 && total_count_sample2 === 0) {
    return 0
  }

  // Bray-Curtis formula= 1 - (2 * lessercount) / (total_count_sample1 + total_count_sample2)
  let distance = 1 - (2 * lesser_count) / (total_count_sample1 + total_count_sample2)
  return distance
}

// Centered Log-Ratio (CLR) transformation for compositional data
function clrTransform(sample: number[]): number[] {
  // Add pseudocount to avoid the log of zero
  const pseudocount = 0.5
  const sample_with_pseudocount = sample.map((x) => x + pseudocount)

  // log transform each value
  const log_values = sample_with_pseudocount.map(x => Math.log(x))
  // add log values together and calculate average
  const sum_log_values = log_values.reduce((sum, x) => sum + x, 0)
  const avg_log_abundance = sum_log_values / sample_with_pseudocount.length

  // Apply CLR transformation: take the log value minus the average log abundance
  return log_values.map(x => x - avg_log_abundance)
}

// Calculate Aitchison distance between two CLR-transformed samples
function aitchisonDistance(sample1: number[], sample2: number[]): number {
  // Transform both samples using CLR
  const clr1 = clrTransform(sample1)
  const clr2 = clrTransform(sample2)

  // Aitchison distance is Euclidean distance in CLR space
  let sum_square_difference = 0
  for (let i = 0; i < clr1.length; i++) {
    const a = clr1[i]
    const b = clr2[i]
    const diff = a - b

    sum_square_difference += diff * diff
  }

  return Math.sqrt(sum_square_difference)
}

// Calculate full distance matrix for all sample pairs
function calculateBetaDiversityMatrix(data: number[][], metric: string = 'bray_curtis'): number[][] {
  const num_samples = data.length
  const distanceMatrix: number[][] = []

  // Initialize matrix with zeros
  for (let i = 0; i < num_samples; i++) {
    distanceMatrix[i] = new Array(num_samples).fill(0)
  }

  // Calculate pairwise distances using selected metric
  for (let i = 0; i < num_samples; i++) {
    for (let j = i + 1; j < num_samples; j++) {
      const distance = metric === 'aitchison'
        ? aitchisonDistance(data[i], data[j])
        : brayCurtisDistance(data[i], data[j])
      distanceMatrix[i][j] = distance
      distanceMatrix[j][i] = distance // Matrix is symmetric
    }
  }

  return distanceMatrix
}

// Parse string value to number, default to 0 for non-numeric
function parseNumeric(value: string | number): number {
  if (typeof value === 'number') return value
  const parsed = parseFloat(value)
  return isNaN(parsed) ? 0 : parsed
}

// Classical MDS / PCoA calculation
function calculatePCoA(distanceMatrix: number[][]): {
  coordinates: number[][],
  explainedVariance: number[]
} {
  const n = distanceMatrix.length

  // Step 1: Square the distance matrix
  const D2 = distanceMatrix.map(row => row.map(d => d * d))

  // Step 2: Apply double centering to get B matrix
  // To get matrix B, you take the matrix of squared distances, subtract the row and column averages so everything is centered around zero,
  // and then multiply by −0.5 to convert those centered distances into an inner-product matrix that can be used for PCoA.
  const rowMeans = D2.map(row => row.reduce((a, b) => a + b, 0) / n)
  const total_mean = rowMeans.reduce((a, b) => a + b, 0) / n

  const B: number[][] = []
  for (let i = 0; i < n; i++) {
    B[i] = []
    for (let j = 0; j < n; j++) {
      B[i][j] = -0.5 * (D2[i][j] - rowMeans[i] - rowMeans[j] + total_mean)
    }
  }

  // Step 3: Eigenvalue decomposition using power iteration
  // Calculate top 10 eigenvalues to get accurate total variance
  const allEigenResults = powerIteration(B, Math.min(10, n))
  const eigenvalues = [allEigenResults.eigenvalues[0], allEigenResults.eigenvalues[1]]
  const eigenvectors = [allEigenResults.eigenvectors[0], allEigenResults.eigenvectors[1]]

  // Step 4: Calculate principal coordinates
  const coordinates: number[][] = []
  for (let i = 0; i < n; i++) {
    coordinates.push([
      eigenvectors[0][i] * Math.sqrt(Math.abs(eigenvalues[0])),
      eigenvectors[1][i] * Math.sqrt(Math.abs(eigenvalues[1]))
    ])
  }

  // Calculate explained variance percentages
  // Total variance = sum of all POSITIVE eigenvalues (not just top 2)
  const totalVariance = allEigenResults.eigenvalues
    .filter(val => val > 1e-10)
    .reduce((sum, val) => sum + val, 0)
  const explainedVariance = eigenvalues.map(val => (val / totalVariance) * 100)

  return { coordinates, explainedVariance }
}

// Power iteration method to find top k eigenvalues and eigenvectors
function powerIteration(matrix: number[][], k: number): {
  eigenvalues: number[],
  eigenvectors: number[][]
} {
  const n = matrix.length
  const eigenvalues: number[] = []
  const eigenvectors: number[][] = []

  // Copy matrix for deflation
  let A = matrix.map(row => [...row])

  for (let iter = 0; iter < k; iter++) {
    // Initialize random vector
    let v = Array(n).fill(0).map(() => Math.random() - 0.5)

    // Normalize
    let norm = Math.sqrt(v.reduce((sum, val) => sum + val * val, 0))
    v = v.map(val => val / norm)

    // Power iteration
    for (let i = 0; i < 100; i++) {
      // Multiply A * v
      const Av = Array(n).fill(0)
      for (let row = 0; row < n; row++) {
        for (let col = 0; col < n; col++) {
          Av[row] += A[row][col] * v[col]
        }
      }

      // Normalize
      norm = Math.sqrt(Av.reduce((sum, val) => sum + val * val, 0))
      v = Av.map(val => val / norm)
    }

    // Calculate eigenvalue (Rayleigh quotient)
    let eigenvalue = 0
    for (let i = 0; i < n; i++) {
      for (let j = 0; j < n; j++) {
        eigenvalue += v[i] * A[i][j] * v[j]
      }
    }

    eigenvalues.push(eigenvalue)
    eigenvectors.push(v)

    // Deflate matrix: A = A - λ * v * v'
    for (let i = 0; i < n; i++) {
      for (let j = 0; j < n; j++) {
        A[i][j] -= eigenvalue * v[i] * v[j]
      }
    }
  }

  return { eigenvalues, eigenvectors }
}

Deno.serve(async (req) => {
  // Handle CORS preflight requests
  if (req.method === 'OPTIONS') {
    return new Response('ok', { headers: corsHeaders })
  }

  const startTime = Date.now()

  try {
    // Parse request body
    const { table_name, row_limit = 50, column_limit = 10, metric = 'bray_curtis' } = await req.json().catch(() => ({}))

    if (!table_name) {
      return new Response(
        JSON.stringify({ success: false, error: 'please select a table' }),
        { headers: { ...corsHeaders, 'Content-Type': 'application/json' }, status: 400 }
      )
    }

    // Limit row and column counts to reasonable maximums, can be adjusted if needed
    const maxRowLimit = 1000
    const maxColLimit = 500
    const validRowLimit = Math.min(Math.max(1, row_limit), maxRowLimit)
    const validColLimit = Math.min(Math.max(2, column_limit), maxColLimit)

    // Connect to PostgreSQL
    const databaseUrl = Deno.env.get('SUPABASE_DB_URL')!
    const pool = new postgres.Pool(databaseUrl, 3, true)
    const connection = await pool.connect()

    try {
      // Verify table exists
      const tableCheck = await connection.queryObject(
        `SELECT EXISTS (
          SELECT FROM information_schema.tables
          WHERE table_schema = '_fd' AND table_name = $1
        )`,
        [table_name]
      )

      if (!tableCheck.rows[0]?.exists) {
        return new Response(
          JSON.stringify({
            success: false,
            error: `Table '${table_name}' not found in _fd schema`
          }),
          { headers: { ...corsHeaders, 'Content-Type': 'application/json' }, status: 404 }
        )
      }

      // Get column names (excluding rowid and first column which is patient ID)
      const columnsResult = await connection.queryObject(
        `SELECT column_name
         FROM information_schema.columns
         WHERE table_schema = '_fd' AND table_name = $1
         AND column_name NOT IN ('rowid')
         ORDER BY ordinal_position
         LIMIT $2`,
        [table_name, validColLimit + 1] // +1 to get sample ID column
      )

      const allColumns = columnsResult.rows.map(row => row.column_name as string)

      // First column is name for sample ID, rest are data columns
      const patientCol = allColumns[0]
      const dataColumns = allColumns.slice(1, validColLimit + 1) // get all the sample names that the user selects

      if (dataColumns.length < 2) {
        return new Response(
          JSON.stringify({
            success: false,
            error: 'Cannot apply beta diversity with less than 2 columns'
          }),
          { headers: { ...corsHeaders, 'Content-Type': 'application/json' }, status: 400 }
        )
      }

      // Build column list for SQL query
      const columnsList = dataColumns.map(col => `"${col}"`).join(', ')

      // Query data
      const dataResult = await connection.queryObject(
        `SELECT ${columnsList}
         FROM _fd."${table_name}"
         LIMIT $1`,
        [validRowLimit]
      )

      if (dataResult.rows.length === 0) {
        return new Response(
          JSON.stringify({
            success: false,
            error: 'No data found in table'
          }),
          { headers: { ...corsHeaders, 'Content-Type': 'application/json' }, status: 404 }
        )
      }

      // Transform data: rows are samples, columns are OTU's
      // We need to transpose: each sample becomes a vector of all the OTU's
      const sampleData: number[][] = []

      for (let colIdx = 0; colIdx < dataColumns.length; colIdx++) {
        const sampleName = dataColumns[colIdx]
        const abundances: number[] = []

        // Collect all abundances for this sample across all OTUs
        for (const row of dataResult.rows) {
          const value = row[sampleName]
          abundances.push(parseNumeric(value as string))
        }

        sampleData.push(abundances)
      }

      // Calculate beta diversity matrix with selected metric
      const distanceMatrix = calculateBetaDiversityMatrix(sampleData, metric)

      // Calculate PCoA coordinates
      const pcoaResult = calculatePCoA(distanceMatrix)

      // Get total column count for metadata
      const totalColsResult = await connection.queryObject(
        `SELECT COUNT(*) as count
         FROM information_schema.columns
         WHERE table_schema = '_fd' AND table_name = $1
         AND column_name NOT IN ('rowid')`,
        [table_name]
      )

      const totalColumns = Number(totalColsResult.rows[0]?.count || 0) - 1 // -1 for patient ID column

      const processingTime = Date.now() - startTime

      // Prepare response
      const responseData = {
        success: true,
        data: {
          distance_matrix: distanceMatrix,
          sample_names: dataColumns,
          row_count: dataResult.rows.length,
          column_count: dataColumns.length,
          total_columns_available: totalColumns,
          metric: metric,
          pcoa_coordinates: pcoaResult.coordinates,
          explained_variance: pcoaResult.explainedVariance
        },
        metadata: {
          table_name,
          processing_time_ms: processingTime,
          row_limit: validRowLimit,
          column_limit: validColLimit
        }
      }

      return new Response(
        JSON.stringify(responseData),
        {
          headers: { ...corsHeaders, 'Content-Type': 'application/json' },
          status: 200,
        },
      )

    } finally {
      connection.release()
    }

  } catch (error) {
    console.error('Error in get-dataset-visualization:', error)
    return new Response(
      JSON.stringify({
        success: false,
        error: error.message || 'Internal server error'
      }),
      {
        headers: { ...corsHeaders, 'Content-Type': 'application/json' },
        status: 500,
      },
    )
  }
})
