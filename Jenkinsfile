pipeline {
    agent any

    environment {
        COMPOSE_PROJECT_NAME = "autoquiz"
    }

    stages {
        stage('Clone Repository') {
            steps {
                git branch: 'main', url: 'https://github.com/ABHISAM2289/Auto-quiz.git'
            }
        }

        stage('Stop Existing Containers') {
            steps {
                dir('Auto-quiz') {
                    sh 'docker-compose down || true'
                }
            }
        }

        stage('Build and Deploy') {
  steps {
    withCredentials([
      file(credentialsId: 'gcloud-service-account', variable: 'GCLOUD_JSON'),
      string(credentialsId: 'GEMINI_API_SUMMARIZER', variable: 'GEMINI_API_KEY')
    ]) {
      dir('Auto-quiz') {
        sh '''
          # Copy service account key to the right place BEFORE docker build
          cp "$GCLOUD_JSON" services/speech_to_text/gcloud.json
          chmod 644 services/speech_to_text/gcloud.json

          export GEMINI_API_KEY=$GEMINI_API_KEY

          docker-compose build
          docker-compose up -d
        '''
      }
    }
  }
}

    post {
        failure {
            echo 'Build failed!'
        }
        success {
            echo 'Build and deployment successful!'
        }
    }
}
